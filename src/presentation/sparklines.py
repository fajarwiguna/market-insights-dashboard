"""Deret penutupan untuk mini-trend kartu KPI."""

SPARK_SOURCES = {
    "USD/IDR": ("yfinance", "USDIDR"),
    "DXY (indeks dolar)": ("yfinance", "DXY"),
    "IHSG (bursa RI)": ("yfinance", "IHSG"),
}


def sparkline_values(report: dict, snapshot: dict, label: str) -> list[float]:
    """Ambil deret harga penutupan harian untuk sparkline (bila datanya ada)."""
    if label in SPARK_SOURCES:
        yf_key, sym = SPARK_SOURCES[label]
        hist = ((snapshot.get(yf_key) or {}).get(sym) or {}).get("history") or []
        nilai = [h.get("close") for h in hist if isinstance(h, dict)]
        return [float(v) for v in nilai if v is not None]
    if label.startswith("Imbal hasil UST"):
        hist = report.get("history_ust10") or []
        return [float(h["close"]) for h in hist if isinstance(h, dict) and h.get("close") is not None]
    return []
