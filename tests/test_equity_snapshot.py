"""Equity ranking, session integrity and cached API contracts without networking."""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "backend" / "src"))
from fastapi import HTTPException
from market_report.domain.equity_snapshot import build_equity_snapshot, rank_stocks, enrich_equity_indicators
from market_report.api.routers import equity
from market_report.services.equity_snapshot_service import _quote_index, session_cutoff
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

    def test_undated_or_unsourced_foreign_data_not_borrowed(self):
        result = build_equity_snapshot(self.source(), {"capital_flow": {"Saham": {"date": "2026-01-01", "today": 123}}})
        self.assertIsNone(result["foreign_flow"]["net_usd_mn"])
        self.assertIsNone(result["coal"]["mtd_pct"])

    def supplemental(self):
        return {"report_id": "published", "capital_flow": {"Saham": {
            "date": "2026-09-30", "unit": "USD juta", "source": "IDX", "periods": {"1D": -100, "1W": -500, "MtD": -1000}}},
            "commodities": {"Coal (Newcastle)": {"date": "2026-10-07", "today": 150, "mtd_pct": 2.3891,
                "source": "Investing.com historical", "source_name": "Investing.com"}},
            "_source_snapshot": {"yfinance": {"USDIDR": {"history": [
                {"date": "2026-09-30", "close": 17000}, {"date": "2026-10-07", "close": 18000}]}}}}

    def test_supplemental_uses_transaction_fx_and_preserves_snapshot(self):
        original = build_equity_snapshot(self.source())
        result = enrich_equity_indicators(original, self.supplemental())
        self.assertEqual(result["foreign_flow"]["net_idr"], -1.7e12)
        self.assertTrue(result["foreign_flow"]["stale"])
        self.assertEqual(result["coal"]["mtd_pct"], 2.3891)
        self.assertIsNone(result["foreign_flow_rows"][0]["wtd"])
        self.assertEqual(result["foreign_flow_rows"][0]["mtd"], -1000)
        self.assertIsNone(original["coal"]["mtd_pct"])
        self.assertEqual(result["stocks"], original["stocks"])

    def test_future_supplemental_rejected_and_zero_is_valid(self):
        report = self.supplemental()
        report["commodities"]["Coal (Newcastle)"]["date"] = "2026-10-08"
        report["capital_flow"]["Saham"]["date"] = "2026-10-08"
        result = build_equity_snapshot(self.source(), report)
        self.assertIsNone(result["coal"]["mtd_pct"])
        self.assertIsNone(result["foreign_flow"]["net_usd_mn"])
        report = self.supplemental()
        report["capital_flow"]["Saham"]["periods"]["1D"] = 0
        report["_source_snapshot"] = {}
        result = build_equity_snapshot(self.source(), report)
        self.assertEqual(result["foreign_flow"]["net_usd_mn"], 0)
        self.assertIsNone(result["foreign_flow"]["net_idr"])

    def test_session_cutoff_prefers_report_session_and_falls_back_to_close(self):
        self.assertEqual(session_cutoff(datetime(2026, 10, 16, 9, 0), "2026-10-16"), "2026-10-16")
        self.assertEqual(session_cutoff(datetime(2026, 10, 16, 16, 30), "2026-10-15"), "2026-10-15")
        self.assertEqual(session_cutoff(datetime(2026, 10, 16, 9, 0)), "2026-10-15")
        self.assertEqual(session_cutoff(datetime(2026, 10, 16, 15, 55)), "2026-10-15")
        self.assertEqual(session_cutoff(datetime(2026, 10, 16, 16, 30)), "2026-10-16")
        self.assertEqual(session_cutoff(datetime(2026, 10, 16, 9, 0), "bukan-tanggal"), "2026-10-15")

    def _symbol_frame(self, sessions):
        import pandas as pd
        index = pd.to_datetime(sessions)
        size = len(sessions)
        return pd.DataFrame({"Close": [100.0 + offset for offset in range(size)],
                             "Volume": [1000] * size, "Stock Splits": [0] * size}, index=index)

    def test_fetch_equity_source_follows_provided_session(self):
        from market_report.services import equity_snapshot_service as service
        sessions = ["2026-10-14", "2026-10-15", "2026-10-16"]
        universe = {"date": "2026-10-16", "complete": True, "stocks": [
            {"symbol": "AAAA.JK", "ticker": "AAAA", "company": "AAAA", "shares_outstanding": 100,
             "market_cap": 0, "sector": "Energy", "quote_price": 102}]}
        with patch.object(service, "_download", lambda yf, symbols: {s: self._symbol_frame(sessions) for s in symbols}), \
             patch.object(service, "discover_equities", lambda yf, now: universe):
            latest = service.fetch_equity_source(session_day="2026-10-16")
            earlier = service.fetch_equity_source(session_day="2026-10-15")
        self.assertEqual((latest["trading_date"], latest["previous_trading_date"]), ("2026-10-16", "2026-10-15"))
        self.assertEqual((earlier["trading_date"], earlier["previous_trading_date"]), ("2026-10-15", "2026-10-14"))
        self.assertEqual(latest["stocks"][0]["date"], "2026-10-16")
        self.assertEqual(latest["indices"]["IHSG"]["date"], "2026-10-16")

    def test_active_report_session_day_reads_active_report(self):
        from market_report.services import equity_snapshot_service as service
        import market_report.services.report_service as report_service
        with patch.object(report_service, "load_report",
                          lambda *a, **k: {"equity_snapshot": {"report_date": "2026-10-16"}}):
            self.assertEqual(service._active_report_session_day(), "2026-10-16")
        with patch.object(report_service, "load_report",
                          lambda *a, **k: {"_source_snapshot": {"yfinance": {"IHSG": {"date": "2026-10-15"}}}}):
            self.assertEqual(service._active_report_session_day(), "2026-10-15")
        with patch.object(report_service, "load_report", return_value=None):
            self.assertIsNone(service._active_report_session_day())

    def test_run_all_forwards_report_session_to_equity(self):
        from contextlib import ExitStack
        import market_report.fetch_data as fetch_data
        import market_report.services.equity_snapshot_service as service
        import market_report.services.international_equity_flow_service as intl
        captured = {}

        def fake_equity(session_day=None):
            captured["session_day"] = session_day
            return {"session_day": session_day}

        stubs = {
            "fetch_market_snapshot": lambda: {"IHSG": {"date": "2026-10-16"}, "USDIDR": {}},
            "fetch_capital_flow": lambda market: {},
            "fetch_antam_gold_price": dict, "fetch_fx_backup": dict, "fetch_phei_yields": dict,
            "fetch_bi_rates": dict, "fetch_macro_indicators": dict, "fetch_monetary_operations": dict,
        }
        with ExitStack() as stack:
            for name, stub in stubs.items():
                stack.enter_context(patch.object(fetch_data, name, stub))
            stack.enter_context(patch.object(intl, "fetch_international_equity_flows", lambda: {}))
            stack.enter_context(patch.object(service, "fetch_equity_source", fake_equity))
            snapshot = fetch_data.run_all(persist=False)
        self.assertEqual(captured["session_day"], "2026-10-16")
        self.assertEqual(snapshot["equity"], {"session_day": "2026-10-16"})

    def test_sector_quote_rejects_live_or_stale_session(self):
        stamp = datetime(2026, 10, 7, 10, tzinfo=timezone.utc).timestamp()
        info = {"regularMarketTime": stamp, "regularMarketPrice": 110, "regularMarketPreviousClose": 100}
        self.assertAlmostEqual(_quote_index(info, "2026-10-07", "2026-10-06")["change_pct"], 10)
        self.assertIsNone(_quote_index(info, "2026-10-06", "2026-10-05"))
        self.assertIsNone(_quote_index(info, "2026-10-08", "2026-10-07"))

    def test_sector_fallback_requires_same_session_and_uses_daily_change(self):
        source = self.source()
        report = {"index_sectors": {
            "Keuangan": {"date": "2026-10-07", "today": 1320.669, "dtd_pct": .0236, "ytd_pct": -14.8, "source": "Yahoo"},
            "Energi": {"date": "2026-10-08", "today": 3200, "dtd_pct": -1.5, "source": "Yahoo"},
            "Kesehatan": {"date": "2026-10-06", "today": 1400, "dtd_pct": .2, "source": "Yahoo"},
            "Teknologi": {"date": "2026-10-07", "today": 5800, "dtd_pct": 0, "source": "Yahoo"},
        }}
        result = build_equity_snapshot(source, report)
        rows = {row["id"]: row for row in result["market_performance"]}
        self.assertEqual(rows["IDXFINANCE"]["level"], 1320.669)
        self.assertEqual(rows["IDXFINANCE"]["change_pct"], .0236)
        self.assertIsNone(rows["IDXENERGY"]["level"])
        self.assertIsNone(rows["IDXHEALTH"]["level"])
        self.assertEqual(rows["IDXTECHNO"]["change_pct"], 0)
        source["indices"]["IDXFINANCE"] = {"last": 1300, "change_pct": .5, "date": "2026-10-07"}
        preserved = build_equity_snapshot(source, report)
        self.assertEqual(next(row for row in preserved["market_performance"] if row["id"] == "IDXFINANCE")["level"], 1300)

    def test_intraday_refresh_retains_exact_completed_sector_sessions(self):
        source = self.source()
        source["indices"]["IHSG"]["prev_date"] = "2026-10-06"
        report = {"index_sectors": {"Keuangan": {"date": "2026-10-08", "today": 900,
                  "dtd_pct": -10, "source": "Yahoo"}}, "_source_snapshot": {"_index_sector_history": {
                  "Keuangan": [{"date": "2025-12-30", "close": 1500}, {"date": "2026-10-06", "close": 1000},
                  {"date": "2026-10-07", "close": 1010}, {"date": "2026-10-08", "close": 900}]}}}
        result = build_equity_snapshot(source, report)
        row = next(row for row in result["market_performance"] if row["id"] == "IDXFINANCE")
        self.assertEqual(row["level"], 1010)
        self.assertAlmostEqual(row["change_pct"], 1)
        self.assertEqual(row["date"], "2026-10-07")
        report["_source_snapshot"]["_index_sector_history"]["Keuangan"].pop(1)
        result = build_equity_snapshot(source, report)
        self.assertIsNone(next(row for row in result["market_performance"] if row["id"] == "IDXFINANCE")["level"])

    def test_analyst_prose_uses_verified_figures_without_provider_or_causal_claims(self):
        report = self.supplemental()
        report["macro_indicators"] = {"Inflasi Indonesia YoY (%)": {"observations": {"2026-08": 3.19, "2026-09": 3.28, "2026-11": 99}}}
        result = build_equity_snapshot(self.source(), report)
        paragraphs = {row["id"]: row["text"] for row in result["narratives"]}
        combined = " ".join(paragraphs.values()).lower()
        for forbidden in ("yahoo", "yfinance", "estimasi", "kapitalisasi", "profit taking", "el nino", "ftse", "msci"):
            self.assertNotIn(forbidden, combined)
        self.assertIn("3,28% YoY", paragraphs["macro"])
        self.assertNotIn("99,00", paragraphs["macro"])
        self.assertIn("2,39% MTD", paragraphs["sector"])
        self.assertIn("AAAA (+10,00%)", paragraphs["sector"])
        self.assertIn("BBBB (−10,00%)", paragraphs["sector"])
        self.assertIn("30 September 2026", paragraphs["foreign"])

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
