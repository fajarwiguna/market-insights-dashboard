"""Uji kontrak dan penerbitan snapshot tanpa akses jaringan."""

import json
import tempfile
import unittest
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))
from market_report.services import report_service


def valid_source_snapshot() -> dict:
    return {
        "generated_at": "2026-10-02T09:00:00+00:00",
        "yfinance": {
            "USDIDR": {"last": 17800.0, "prev": 17750.0, "change_pct": 0.2817,
                       "date": "2026-10-02", "history": []},
            "IHSG": {"last": 6100.0, "prev": 6050.0, "change_pct": 0.8264,
                     "date": "2026-10-02", "history": []},
            "US10Y": {"last": 4.1, "prev": 4.0, "date": "2026-10-02", "history": []},
            "US5Y": {"last": 3.8, "prev": 3.7, "date": "2026-10-02", "history": []},
        },
        "fx_backup": {},
        "phei": {
            "as_of_date": "01-Oktober-2026",
            "as_of_label": "per 01-Oktober-2026",
            "yield_curve": {
                "5": {"today": 6.5, "yesterday": 6.4, "change_bp": 10.0},
                "10": {"today": 7.0, "yesterday": 6.9, "change_bp": 10.0},
            },
        },
        "bi": {"bi_rate": 5.75, "indonia": 6.0, "jisdor": 17800},
    }


class ReportPipelineTests(unittest.TestCase):
    def test_publish_uses_the_supplied_snapshot_and_persists_one_version(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report_path = root / "report_data.json"
            snapshot_path = root / "snapshot.json"
            source_snapshot = valid_source_snapshot()

            report = report_service.publish_snapshot(
                source_snapshot, report_path=report_path, snapshot_path=snapshot_path
            )

            saved_report = json.loads(report_path.read_text(encoding="utf-8"))
            saved_snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            self.assertEqual(report["schema_version"], 2)
            self.assertFalse(report["is_demo"])
            self.assertEqual(report["_source_snapshot"], source_snapshot)
            self.assertEqual(saved_report["_source_snapshot"], saved_snapshot)
            self.assertEqual(saved_snapshot, source_snapshot)

    def test_invalid_snapshot_does_not_replace_active_report_or_snapshot(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            root = Path(temporary_directory)
            report_path = root / "report_data.json"
            snapshot_path = root / "snapshot.json"
            report_service.publish_snapshot(
                valid_source_snapshot(), report_path=report_path, snapshot_path=snapshot_path
            )
            previous_report = report_path.read_bytes()
            previous_snapshot = snapshot_path.read_bytes()
            empty_snapshot = {"generated_at": "2026-10-02T10:00:00+00:00", "yfinance": {}}

            with self.assertRaisesRegex(RuntimeError, "Laporan (aktif )?sebelumnya tetap dipakai"):
                report_service.publish_snapshot(
                    empty_snapshot, report_path=report_path, snapshot_path=snapshot_path
                )

            self.assertEqual(report_path.read_bytes(), previous_report)
            self.assertEqual(snapshot_path.read_bytes(), previous_snapshot)

    def test_demo_is_saved_separately_and_marked(self):
        with tempfile.TemporaryDirectory() as temporary_directory:
            demo_path = Path(temporary_directory) / "demo_report_data.json"
            live_path = Path(temporary_directory) / "report_data.json"
            live_path.write_text('{"report_date": "live"}', encoding="utf-8")

            report_service.save_demo_report({"report_date": "contoh"}, demo_path)

            demo = json.loads(demo_path.read_text(encoding="utf-8"))
            self.assertTrue(demo["is_demo"])
            self.assertEqual(demo["schema_version"], 1)
            self.assertEqual(json.loads(live_path.read_text(encoding="utf-8")),
                             {"report_date": "live"})


if __name__ == "__main__":
    unittest.main()
