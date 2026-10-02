"""Alur bersama untuk membentuk, memvalidasi, dan menerbitkan laporan pasar."""

import json
import logging
import math
from pathlib import Path


_DATA_DIR = Path(__file__).resolve().parents[2] / "data"
_REPORT_PATH = _DATA_DIR / "report_data.json"
_SNAPSHOT_PATH = _DATA_DIR / "snapshot.json"
_DEMO_REPORT_PATH = _DATA_DIR / "demo_report_data.json"
_logger = logging.getLogger(__name__)


def load_report(path: Path | None = None) -> dict | None:
    """Baca laporan aktif terakhir yang sudah diterbitkan."""
    report_path = path or _REPORT_PATH
    if not report_path.exists():
        return None
    with report_path.open(encoding="utf-8") as source:
        return json.load(source)


def load_snapshot(path: Path | None = None) -> dict:
    """Baca snapshot sumber yang sama dengan laporan aktif."""
    if path is None:
        report = load_report()
        if report and isinstance(report.get("_source_snapshot"), dict):
            return report["_source_snapshot"]
        snapshot_path = _SNAPSHOT_PATH
    else:
        snapshot_path = path
    if not snapshot_path.exists():
        return {}
    try:
        with snapshot_path.open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, json.JSONDecodeError):
        return {}


def validate_report(report: dict) -> None:
    """Tolak laporan live yang tidak berisi sedikitnya dua observasi pasar valid."""
    if not isinstance(report, dict) or report.get("is_demo"):
        raise ValueError("Hasil pipeline live harus berupa laporan pasar non-demo.")

    jumlah = 0
    for section in ("fx", "indices", "yields", "commodities"):
        values = report.get(section)
        if not isinstance(values, dict):
            continue
        for row in values.values():
            if not isinstance(row, dict):
                continue
            value = row.get("today")
            if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
                jumlah += 1
    if jumlah < 2:
        raise RuntimeError(
            "Data pasar terbaru tidak cukup (kurang dari 2 instrumen berhasil dibaca). "
            "Laporan sebelumnya tetap dipakai; coba perbarui lagi nanti."
        )


def publish_snapshot(snapshot: dict, *, report_path: Path | None = None,
                     snapshot_path: Path | None = None) -> dict:
    """Bangun dan validasi laporan dari payload snapshot yang diberikan, lalu terbitkan."""
    from calculate import build_report_data, persist_json_data, persist_report_data

    report = build_report_data(snapshot)
    report["schema_version"] = 1
    report["_source_snapshot"] = snapshot
    validate_report(report)

    # File laporan adalah satu-satunya penanda data aktif dan ditulis atomik.
    persist_report_data(report, report_path or _REPORT_PATH)

    # Snapshot terpisah hanya menjadi salinan diagnostik; UI membaca salinan
    # yang tertanam pada laporan aktif agar kedua tampilan memakai versi sama.
    try:
        persist_json_data(snapshot, snapshot_path or _SNAPSHOT_PATH)
    except OSError:
        _logger.exception("Gagal menyimpan salinan snapshot diagnostik")
    return report


def run_live_pipeline() -> dict:
    """Ambil sumber satu kali, bentuk laporan dari payload itu, lalu terbitkan."""
    from fetch_data import run_all

    snapshot = run_all(persist=False)
    return publish_snapshot(snapshot)


def rebuild_from_saved_snapshot() -> dict:
    """Bangun ulang laporan dengan snapshot yang sudah tersimpan tanpa fetch."""
    snapshot = load_snapshot()
    if not snapshot:
        raise RuntimeError("Snapshot sumber belum tersedia untuk dibangun ulang.")
    return publish_snapshot(snapshot)


def save_demo_report(report: dict, path: Path | None = None) -> Path:
    """Simpan data demo terpisah agar tidak mengganti laporan live yang aktif."""
    from calculate import persist_report_data

    report = dict(report)
    report.update({"schema_version": 1, "is_demo": True})
    demo_path = path or _DEMO_REPORT_PATH
    persist_report_data(report, demo_path)
    return demo_path
