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


def _clean_points(points) -> list[dict]:
    result = []
    for point in points or []:
        if not isinstance(point, dict) or point.get("close") is None:
            continue
        date = source_date_iso(point.get("date"))
        if date:
            result.append({"dates": date, "close": float(point["close"])})
    return result


def instrument_history(instrument_id: str) -> list[dict] | None:
    """Kembalikan list, list kosong bila ID dikenal tanpa data, atau None jika ID asing."""
    instrument_id = instrument_id.lower()
    if instrument_id == "sbn-10y":
        return [{"dates": point["date"], "close": float(point["close"])}
                for point in history_service.load_sbn_history()]

    symbol = _SNAPSHOT_SYMBOLS.get(instrument_id)
    if symbol is None:
        return None
    report = report_service.load_report()
    if not report:
        return []
    if instrument_id == "us-10y":
        points = _clean_points(report.get("history_ust10"))
        if points:
            return points
    snapshot = report.get("_source_snapshot") or {}
    quote = ((snapshot.get("yfinance") or {}).get(symbol) or {})
    return _clean_points(quote.get("history"))
