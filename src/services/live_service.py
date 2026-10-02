"""Pengambilan harga terkini dan penggabungan dengan snapshot harian."""

import json
import threading
import time

from domain.market_analysis import market_facts
from domain.market_data import find_key


LIVE_SPOT = {
    "fx": {"USD/IDR": "USDIDR=X", "EUR/IDR": "EURIDR=X", "CNY/IDR": "CNYIDR=X",
           "JPY/IDR": "JPYIDR=X", "DXY": "DX-Y.NYB"},
    "indices": {"IHSG (ID)": "^JKSE", "DJI (US)": "^DJI"},
    "yields": {"US Treasury 10 Tahun": "^TNX", "US Treasury 5 Tahun": "^FVX"},
    "commodities": {"Gold (USD/oz)": "GC=F", "Brent Crude": "BZ=F", "WTI Crude": "CL=F"},
}

_LIVE_CACHE_LOCK = threading.Lock()
_LIVE_CACHE_DATA: dict = {}
_LIVE_CACHE_TIME = 0.0


def fetch_live_prices_cached(ttl_seconds: int = 30) -> dict:
    """Cache harga intraday per proses supaya API tidak mengulang fetch untuk tiap request."""
    global _LIVE_CACHE_DATA, _LIVE_CACHE_TIME
    with _LIVE_CACHE_LOCK:
        if _LIVE_CACHE_DATA and time.monotonic() - _LIVE_CACHE_TIME < ttl_seconds:
            return json.loads(json.dumps(_LIVE_CACHE_DATA))
        _LIVE_CACHE_DATA = fetch_live_prices()
        _LIVE_CACHE_TIME = time.monotonic()
        return json.loads(json.dumps(_LIVE_CACHE_DATA))


def fetch_live_prices() -> dict:
    """
    Ambil harga terkini dari Yahoo Finance untuk instrumen pada LIVE_SPOT.

    Cache dikelola oleh entry point Streamlit; kegagalan sumber dikembalikan sebagai data kosong.
    """
    datar = {f"{seksi}|{label}": simbol
             for seksi, isi in LIVE_SPOT.items() for label, simbol in isi.items()}
    try:
        from fetch_data import fetch_live_spot
        return fetch_live_spot(datar)
    except Exception as e:  # jaringan mati / sumber menolak — pemanggil pakai snapshot
        return {"_error": str(e)}


def pasang_angka_langsung(report: dict, langsung: dict) -> tuple[dict, list[str]]:
    """
    Salin laporan lalu timpa angkanya dengan harga terkini (intraday).

    Nilai snapshot disimpan sebagai "snapshot_today" sebagai pembanding, dan
    spread SBN–UST dihitung ulang supaya konsisten. Hanya instrumen yang sudah
    ada di laporan yang diperbarui — tidak ada baris instruksi baru.
    """
    view = json.loads(json.dumps(report))
    diperbarui: list[str] = []
    for seksi, isi in LIVE_SPOT.items():
        tujuan = view.get(seksi)
        if not isinstance(tujuan, dict):
            continue
        for label, simbol in isi.items():
            kunci = find_key(tujuan, label)
            if not kunci:
                continue
            q = langsung.get(f"{seksi}|{label}") or {}
            harga = q.get("meta_price") if q.get("meta_price") is not None else q.get("last")
            if harga is None:
                continue
            lama = dict(tujuan[kunci] or {})
            sebelumnya = q.get("prev") if q.get("prev") is not None else lama.get("prev")
            baru = dict(lama)
            baru["snapshot_today"] = lama.get("today")
            baru["today"] = float(harga)
            if sebelumnya is not None:
                baru["prev"] = float(sebelumnya)
                if sebelumnya:
                    delta = float(harga) - float(sebelumnya)
                    baru["change_pct"] = round(delta / float(sebelumnya) * 100, 4)
                    baru["change_bp"] = round(delta * 100, 2)
            baru["date"] = q.get("date") or lama.get("date")
            baru["source"] = f"Yahoo Finance Chart API — {simbol} (harga terkini)"
            baru["live"] = True
            tujuan[kunci] = baru
            diperbarui.append(kunci)

    f = market_facts(view)
    sbn, ust = f["sbn10"].get("today"), f["ust10"].get("today")
    if sbn is not None and ust is not None:
        view["spread_sbn10_ust10_bp"] = round((float(sbn) - float(ust)) * 100, 2)
    view["live_at"] = langsung.get("_fetched_at")
    view["live_error"] = langsung.get("_error")
    return view, diperbarui
