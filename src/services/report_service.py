"""Membaca snapshot laporan dan menjalankan pipeline pembaruan data."""

import json
from pathlib import Path


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"


def load_report() -> dict | None:
    """Baca angka laporan yang terakhir disimpan pipeline."""
    path = _DATA_DIR / "report_data.json"
    if not path.exists():
        return None
    with path.open(encoding="utf-8") as source:
        return json.load(source)


def load_snapshot() -> dict:
    """Baca snapshot mentah; kegagalan atau file yang belum ada menghasilkan dict kosong."""
    path = _DATA_DIR / "snapshot.json"
    if not path.exists():
        return {}
    try:
        with path.open(encoding="utf-8") as source:
            return json.load(source)
    except Exception:
        return {}


def run_live_pipeline() -> dict:
    """Ambil data baru dan simpan hanya bila berisi data pasar yang layak."""
    from fetch_data import run_all
    from calculate import build_report_data, persist_report_data

    run_all()
    report = build_report_data(persist=False)
    market_values = sum(
        1
        for section in ("fx", "indices", "yields", "commodities")
        for row in (report.get(section) or {}).values()
        if isinstance(row, dict) and isinstance(row.get("today"), (int, float))
    )
    if market_values < 2:
        raise RuntimeError(
            "Data pasar terbaru tidak cukup (kurang dari 2 instrumen berhasil dibaca). "
            "Laporan sebelumnya tetap dipakai; coba perbarui lagi nanti."
        )
    persist_report_data(report)
    return report
