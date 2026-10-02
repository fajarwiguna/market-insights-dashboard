"""Penyimpanan riwayat harian SBN 10 tahun untuk grafik dashboard."""

import json
from datetime import datetime
from pathlib import Path


_HISTORY_PATH = Path(__file__).resolve().parents[2] / "data" / "history_sbn.json"


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
    history_path = path or _HISTORY_PATH
    if not history_path.exists():
        return []
    try:
        data = json.loads(history_path.read_text(encoding="utf-8"))
    except Exception:
        return []
    return [
        point for point in data
        if isinstance(point, dict) and point.get("date") and point.get("close") is not None
    ][-30:]


def record_sbn_history(value, report_date: str | None = None,
                       path: Path | None = None) -> list[dict]:
    """Tambah atau perbarui satu titik SBN menurut tanggal yang diterbitkan sumber."""
    history_path = path or _HISTORY_PATH
    if value is None or not report_date:
        return load_sbn_history(history_path)

    date = source_date_iso(report_date)
    if date is None:
        return load_sbn_history(history_path)
    previous = load_sbn_history(history_path)
    updated = sorted(
        [point for point in previous if point["date"] != date]
        + [{"date": date, "close": float(value)}],
        key=lambda point: point["date"],
    )[-30:]
    if updated != previous:
        try:
            history_path.parent.mkdir(parents=True, exist_ok=True)
            history_path.write_text(json.dumps(updated, ensure_ascii=False, indent=2), encoding="utf-8")
        except Exception:
            return previous
    return updated
