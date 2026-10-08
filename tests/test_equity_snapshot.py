"""Equity ranking, session integrity and cached API contracts without networking."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
from fastapi import HTTPException
from market_report.domain.equity_snapshot import build_equity_snapshot, rank_stocks
from market_report.api.routers import equity
from market_report.services.equity_snapshot_service import _quote_index
from datetime import datetime, timezone


class EquityTests(unittest.TestCase):
    def source(self):
        return {"snapshot_id": "test", "trading_date": "2026-10-07", "previous_trading_date": "2026-10-06",
                "indices": {"IHSG": {"last": 7100, "prev": 7000, "change_pct": 100 / 70}},
                "universe_count": 4, "stocks": [
                    {"ticker": ticker, "company": ticker, "date": "2026-10-07", "prev_date": "2026-10-06",
                     "previous_close": 100, "close": close, "shares_outstanding": shares, "sector": "Energy"}
                    for ticker, close, shares in (("AAAA", 110, 100), ("BBBB", 90, 200), ("CCCC", 100, 100))]}

    def test_weighted_points_and_ranking(self):
        result = build_equity_snapshot(self.source())
        self.assertEqual([r["ticker"] for r in result["market_leaders"]], ["AAAA"])
        self.assertEqual([r["ticker"] for r in result["market_laggards"]], ["BBBB"])
        self.assertAlmostEqual(result["market_leaders"][0]["contribution_points"], 175)
        self.assertAlmostEqual(result["market_laggards"][0]["contribution_points"], -350)
        self.assertEqual(result["coverage"]["ratio"], .75)
        self.assertFalse(result["coverage"]["membership_verified"])
        self.assertEqual(len(result["market_performance"]), 19)
        self.assertIsNone(result["market_performance"][0]["level"])

    def test_invalid_previous_session_split_and_missing_shares_excluded(self):
        for field, value in (("prev_date", "2026-10-05"), ("split_detected", True), ("shares_outstanding", None), ("close", float("nan"))):
            with self.subTest(field=field):
                source = self.source()
                source["stocks"][0][field] = value
                result = build_equity_snapshot(source)
                self.assertEqual(result["coverage"]["valid_count"], 2)
                self.assertIn("AAAA", result["coverage"]["excluded_tickers"])
                self.assertEqual(result["market_leaders"], [])

    def test_unrounded_rank_sign_limit_and_deterministic_ties(self):
        rows = [{"ticker": f"S{i:03}", "contribution_points": i / 10000} for i in range(-20, 21)]
        rows += [{"ticker": "invalid", "contribution_points": float("inf")}]
        leaders, laggards = rank_stocks(rows)
        self.assertEqual(len(leaders), 10)
        self.assertEqual(len(laggards), 10)
        self.assertEqual(leaders[0]["contribution_points"], .002)
        self.assertEqual(laggards[0]["contribution_points"], -.002)
        self.assertEqual(rank_stocks([{ "ticker": x, "contribution_points": 1} for x in ["ZZZZ", "AAAA"]])[0][0]["ticker"], "AAAA")

    def test_yahoo_only_never_borrows_foreign_data(self):
        result = build_equity_snapshot(self.source(), {"capital_flow": {"Saham": {"date": "2026-01-01", "today": 123}}})
        self.assertIsNone(result["foreign_flow"]["net_usd_mn"])
        self.assertIsNone(result["coal"]["mtd_pct"])

    def test_sector_quote_rejects_live_or_stale_session(self):
        stamp = datetime(2026, 10, 7, 10, tzinfo=timezone.utc).timestamp()
        info = {"regularMarketTime": stamp, "regularMarketPrice": 110, "regularMarketPreviousClose": 100}
        self.assertAlmostEqual(_quote_index(info, "2026-10-07", "2026-10-06")["change_pct"], 10)
        self.assertIsNone(_quote_index(info, "2026-10-06", "2026-10-05"))
        self.assertIsNone(_quote_index(info, "2026-10-08", "2026-10-07"))

    @patch.object(equity, "load_report", return_value={})
    @patch.object(equity, "load_equity_snapshot", return_value={})
    def test_api_no_data_returns_404(self, *_):
        with self.assertRaises(HTTPException) as caught:
            equity.latest_equity()
        self.assertEqual(caught.exception.status_code, 404)

    @patch.object(equity, "load_report")
    @patch.object(equity, "load_equity_snapshot")
    def test_api_selects_latest_valid_avoiding_failed_refresh(self, cached, published):
        cached.return_value = {"report_id": "old", "status": "partial", "report_date": "2026-10-06"}
        published.return_value = {"equity_snapshot": {"report_id": "failed", "status": "unavailable", "report_date": "2026-10-07"}}
        self.assertEqual(equity.latest_equity()["report_id"], "old")
        published.return_value["equity_snapshot"]["status"] = "partial"
        self.assertEqual(equity.latest_equity()["report_id"], "failed")


if __name__ == "__main__":
    unittest.main()
