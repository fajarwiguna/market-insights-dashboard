"""Commodity calendar returns use the same provider's dated daily closes."""

import base64
from datetime import datetime, timezone
import gzip
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
from market_report.calculate import build_report_data
from market_report.services import commodity_history_service as service


HISTORY = [
    {"date": "2025-12-31", "close": 100},
    {"date": "2026-09-30", "close": 125},
    {"date": "2026-10-02", "close": 140},
    {"date": "2026-10-07", "close": 150},
    {"date": "2026-10-08", "close": 149.45},
]


class CommodityHistoryTests(unittest.TestCase):
    def test_chart_decode_cache_and_offline_fallback(self):
        rows = [[datetime.fromisoformat(point["date"]).replace(tzinfo=timezone.utc).timestamp(),
                 point["close"]] for point in HISTORY]
        payload = {"series": [{"symbol": "XAL1:COM", "data": rows + [[0, True], [0, -1], []]}]}
        compressed = gzip.compress(json.dumps(payload).encode())
        key = service.TE_CHART_ENCODING_KEY
        encoded = base64.b64encode(bytes(value ^ key[index % len(key)]
                                       for index, value in enumerate(compressed))).decode()
        response = Mock()
        response.json.return_value = encoded
        with tempfile.TemporaryDirectory() as directory, \
                patch.object(service, "market_data_directory", return_value=Path(directory)), \
                patch.object(service.requests, "get", return_value=response) as get:
            self.assertEqual(service._trading_economics_history("XAL1:COM"), HISTORY)
            self.assertEqual(get.call_args.kwargs["params"], {"span": "1y", "interval": "1d"})
            get.side_effect = requests.ConnectionError("offline")
            self.assertEqual(service._trading_economics_history("XAL1:COM"), HISTORY)
            get.side_effect = None
            response.json.return_value = "invalid encoding"
            self.assertEqual(service._trading_economics_history("XAL1:COM"), HISTORY)

    def test_coal_and_cpo_report_contains_calendar_returns(self):
        market = {}
        for key, (slug, _) in service.TE_SERIES.items():
            market[key] = {"last": 149.45, "prev": 150, "date": "2026-10-08",
                           "source": f"https://tradingeconomics.com/commodity/{slug}",
                           "dtd_pct": -0.53, "rolling_1m_pct": 1.43}
        snapshot = {"yfinance": market}
        with patch.object(service, "_trading_economics_history", return_value=HISTORY), \
                patch.object(service, "_investing_history") as alternative:
            service.enrich_commodity_history(snapshot, [])
            alternative.assert_not_called()
        report = build_report_data(snapshot)
        for label in ("Coal (Newcastle)", "CPO (Bursa Malaysia)"):
            row = report["commodities"][label]
            self.assertEqual(row["wtd_pct"], round((149.45 / 140 - 1) * 100, 4))
            self.assertEqual(row["mtd_pct"], round((149.45 / 125 - 1) * 100, 4))
            self.assertEqual(row["ytd_pct"], 49.45)
            self.assertEqual(row["rolling_1m_pct"], 1.43)
            self.assertEqual(row["prev_date"], "2026-10-07")
            self.assertEqual(row["availability"], "available")

    def test_current_quote_wins_and_future_chart_points_are_excluded(self):
        current = {"last": 151, "date": "2026-10-07",
                   "source": "https://tradingeconomics.com/commodity/coal"}
        snapshot = {"yfinance": {"NEWCASTLE_COAL": current}}
        other_provider = {"_source_snapshot": {"yfinance": {"NEWCASTLE_COAL": {
            "source": "Investing.com", "history": [{"date": "2025-12-31", "close": 1}]}}}}
        with patch.object(service, "_trading_economics_history", return_value=HISTORY):
            service.enrich_commodity_history(snapshot, [other_provider])
        self.assertEqual(current["history"][-1], {"date": "2026-10-07", "close": 151})
        self.assertEqual(current["history"][0]["close"], 100)
        self.assertEqual(current["last"], 151)

    def test_missing_baselines_are_not_replaced_with_rolling_returns(self):
        current = {"last": 149.45, "date": "2026-10-08", "rolling_1m_pct": 1.43,
                   "source": "https://tradingeconomics.com/commodity/coal"}
        snapshot = {"yfinance": {"NEWCASTLE_COAL": current}}
        with patch.object(service, "_trading_economics_history", return_value=[]), \
                patch.object(service, "_investing_history", return_value=None):
            service.enrich_commodity_history(snapshot, [])
        row = build_report_data(snapshot)["commodities"]["Coal (Newcastle)"]
        for period in ("wtd", "mtd", "ytd"):
            self.assertIsNone(row[f"{period}_pct"])
        self.assertEqual(current["availability"], "partial")


if __name__ == "__main__":
    unittest.main()