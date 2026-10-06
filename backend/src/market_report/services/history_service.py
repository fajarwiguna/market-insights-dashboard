"""Penyimpanan riwayat harian SBN 10 tahun untuk grafik dashboard."""

from datetime import datetime
from pathlib import Path
import re

from market_report.infrastructure.repositories.history_repository import (
    JsonSbnHistoryRepository,
    configured_history_repository,
)
from market_report.config import market_data_directory


_HISTORY_PATH = market_data_directory() / "history_sbn.json"
MAX_HISTORY_POINTS = 420  # enough observations for a prior-year baseline


def source_date_iso(value) -> str | None:
    """Normalisasi tanggal ISO serta nama bulan Indonesia/Inggris dari PHEI."""
    raw = str(value or "").strip()
    try:
        return datetime.fromisoformat(raw[:10]).strftime("%Y-%m-%d")
    except ValueError:
        pass
    aliases = (
        ("jan", "januari", "january"), ("feb", "februari", "february"),
        ("mar", "maret", "march"), ("apr", "april"), ("may", "mei"),
        ("jun", "juni", "june"), ("jul", "juli", "july"),
        ("aug", "agu", "agustus", "august"), ("sep", "september"),
        ("oct", "okt", "oktober", "october"), ("nov", "november"),
        ("dec", "des", "desember", "december"),
    )
    months = {name: month for month, names in enumerate(aliases, 1) for name in names}
    try:
        day, month, year = re.split(r"[\s,./-]+", raw.strip().rstrip(".,"))
        month_number = int(month) if month.isdigit() else months[month.lower()]
        return datetime(int(year), month_number, int(day)).strftime("%Y-%m-%d")
    except (ValueError, KeyError):
        return None


def load_sbn_history(path: Path | None = None) -> list[dict]:
    """Baca histori SBN yang valid untuk grafik dan perbandingan tahunan."""
    repository = JsonSbnHistoryRepository(path) if path is not None else configured_history_repository(_HISTORY_PATH)
    return repository.list(limit=MAX_HISTORY_POINTS)


def record_sbn_history(value, report_date: str | None = None,
                       path: Path | None = None) -> list[dict]:
    """Tambah atau perbarui satu titik SBN menurut tanggal yang diterbitkan sumber."""
    repository = JsonSbnHistoryRepository(path) if path is not None else configured_history_repository(_HISTORY_PATH)
    if value is None or not report_date:
        return repository.list(limit=MAX_HISTORY_POINTS)

    date = source_date_iso(report_date)
    if date is None:
        return repository.list(limit=MAX_HISTORY_POINTS)
    try:
        return repository.upsert(date, float(value), limit=MAX_HISTORY_POINTS)
    except OSError:
        return repository.list(limit=MAX_HISTORY_POINTS)
