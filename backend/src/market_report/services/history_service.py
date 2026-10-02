"""Penyimpanan riwayat harian SBN 10 tahun untuk grafik dashboard."""

from datetime import datetime
from pathlib import Path

from market_report.infrastructure.repositories.history_repository import (
    JsonSbnHistoryRepository,
    configured_history_repository,
)


_HISTORY_PATH = Path(__file__).resolve().parents[4] / "data" / "history_sbn.json"


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
        day, month, year = raw.split("-")
        return datetime(int(year), months[month.lower()], int(day)).strftime("%Y-%m-%d")
    except (ValueError, KeyError):
        return None


def load_sbn_history(path: Path | None = None) -> list[dict]:
    """Baca hingga 30 titik riwayat SBN yang valid."""
    repository = JsonSbnHistoryRepository(path) if path is not None else configured_history_repository(_HISTORY_PATH)
    return repository.list(limit=30)


def record_sbn_history(value, report_date: str | None = None,
                       path: Path | None = None) -> list[dict]:
    """Tambah atau perbarui satu titik SBN menurut tanggal yang diterbitkan sumber."""
    repository = JsonSbnHistoryRepository(path) if path is not None else configured_history_repository(_HISTORY_PATH)
    if value is None or not report_date:
        return repository.list(limit=30)

    date = source_date_iso(report_date)
    if date is None:
        return repository.list(limit=30)
    try:
        return repository.upsert(date, float(value), limit=30)
    except OSError:
        return repository.list(limit=30)
