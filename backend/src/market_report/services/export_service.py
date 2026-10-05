"""Penyusunan berkas PDF dari data yang sedang ditampilkan dashboard."""

import io
import json
import os
import tempfile
from pathlib import Path

from market_report.report_pdf import build_pdf


def build_report_pdf(report_json: str, sbn_json: str) -> tuple[bytes, str]:
    """Bangun PDF satu halaman beserta grafik dari riwayat versi laporan."""
    report = json.loads(report_json)
    sbn_history = json.loads(sbn_json)
    if not isinstance(report.get("_sbn_history"), list):
        report["_sbn_history"] = sbn_history if isinstance(sbn_history, list) else []
    return build_pdf(report, stream=io.BytesIO())


def save_report_pdf(
    report: dict, sbn_history: list[dict], report_dir: Path, *, storage_prefix: str = ""
) -> tuple[Path, str]:
    """Buat dan simpan PDF untuk laporan yang baru diterbitkan."""
    payload, filename = build_report_pdf(
        json.dumps(report, ensure_ascii=False, default=str),
        json.dumps(sbn_history, ensure_ascii=False, default=str),
    )
    destination = Path(report_dir) / f"{storage_prefix}{filename}"
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary_path = None
    try:
        with tempfile.NamedTemporaryFile(dir=destination.parent, suffix=".tmp", delete=False) as output:
            temporary_path = Path(output.name)
            output.write(payload)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, destination)
    finally:
        if temporary_path is not None:
            temporary_path.unlink(missing_ok=True)
    return destination, filename
