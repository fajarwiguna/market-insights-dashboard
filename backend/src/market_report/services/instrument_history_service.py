"""Penyedia riwayat instrumen yang memang tersimpan pada report/snapshot."""

from market_report.services import history_service, report_service
from market_report.services.history_service import source_date_iso


_SNAPSHOT_SYMBOLS = {
    "usd-idr": "USDIDR",
    "dxy": "DXY",
    "ihsg": "IHSG",
    "dji": "DJI",
    "us-5y": "US5Y",
    "us-10y": "US10Y",
    "gold": "GOLD",
    "brent": "BRENT",
    "wti": "WTI",
    "eur-idr": "EURIDR",
    "cny-idr": "CNYIDR",
    "jpy-idr": "JPYIDR",
}


class ReportVersionNotFound(LookupError):
    pass


def _clean_points(points) -> list[dict]:
    result = []
    for point in points or []:
        if not isinstance(point, dict) or point.get("close") is None:
            continue
        date = source_date_iso(point.get("date"))
        if date:
            result.append({"dates": date, "close": float(point["close"])})
    return result


def instrument_history(instrument_id: str, report_id: str | None = None) -> list[dict] | None:
    """Kembalikan list, list kosong bila ID dikenal tanpa data, atau None jika ID asing."""
    instrument_id = instrument_id.lower()
    if instrument_id == "sbn-10y" and report_id is None:
        return [{"dates": point["date"], "close": float(point["close"])}
                for point in history_service.load_sbn_history()]

    symbol = _SNAPSHOT_SYMBOLS.get(instrument_id)
    if symbol is None and instrument_id != "sbn-10y":
        return None
    report = report_service.load_report_version(report_id) if report_id else report_service.load_report()
    if report is None and report_id:
        raise ReportVersionNotFound("Versi laporan tidak ditemukan.")
    if not report:
        return []
    if instrument_id == "sbn-10y":
        # Older versions without frozen history must not borrow today's series.
        return _clean_points(report.get("_sbn_history") or
                             (report.get("_source_snapshot") or {}).get("_sbn_history"))
    if instrument_id == "us-10y":
        points = _clean_points(report.get("history_ust10"))
        if points:
            return points
    snapshot = report.get("_source_snapshot") or {}
    quote = ((snapshot.get("yfinance") or {}).get(symbol) or {})
    return _clean_points(quote.get("history"))
