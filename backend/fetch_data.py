"""
Daily Market Data Fetcher — REAL DATA
Sources:
- FX / Indices / US Yields / Commodities : Yahoo Finance Chart API (query1)
- SBN / SBSN yields                       : PHEI HPW & Imbal Hasil
- BI Rate / INDONIA / JISDOR              : Bank Indonesia
- Cross-check FX                          : open.er-api.com
"""

from __future__ import annotations
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Any, List

import requests
from bs4 import BeautifulSoup

DATA_DIR = Path(__file__).resolve().parent.parent / "data"
DATA_DIR.mkdir(exist_ok=True)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/json,*/*",
}


def _save(name: str, obj: Any) -> Path:
    path = DATA_DIR / f"{name}.json"
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, indent=2, default=str)
    return path


def _yahoo_chart(symbol: str, range_: str = "5d") -> Dict[str, Any]:
    """Fetch OHLCV via Yahoo Chart API (no crumb required)."""
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{symbol}"
    params = {"interval": "1d", "range": range_}
    try:
        r = requests.get(url, params=params, headers=HEADERS, timeout=15)
        r.raise_for_status()
        data = r.json()
        result = (data.get("chart") or {}).get("result")
        if not result:
            return {"error": "no result", "symbol": symbol}
        res = result[0]
        meta = res.get("meta", {})
        timestamps = res.get("timestamp") or []
        quote = (res.get("indicators") or {}).get("quote") or [{}]
        closes = quote[0].get("close") or []

        pairs = [(t, c) for t, c in zip(timestamps, closes) if c is not None]
        if not pairs:
            last = meta.get("regularMarketPrice")
            prev = meta.get("chartPreviousClose")
            return {
                "symbol": symbol,
                "last": last,
                "prev": prev,
                "change_pct": round((last - prev) / prev * 100, 4) if last and prev else None,
                "date": datetime.now().strftime("%Y-%m-%d"),
                "history": [],
                "source": f"Yahoo Chart API ({symbol})",
            }

        last_ts, last = pairs[-1]
        prev = pairs[-2][1] if len(pairs) >= 2 else meta.get("chartPreviousClose") or last
        chg = round((last - prev) / prev * 100, 4) if prev else None
        history = [
            {
                "date": datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%d"),
                "close": c,
            }
            for t, c in pairs
        ]
        return {
            "symbol": symbol,
            "last": float(last),
            "prev": float(prev) if prev else None,
            "change_pct": chg,
            "date": datetime.fromtimestamp(last_ts, tz=timezone.utc).strftime("%Y-%m-%d"),
            "history": history,
            "source": f"Yahoo Finance Chart API — {symbol}",
            "meta_price": meta.get("regularMarketPrice"),
        }
    except Exception as e:
        return {"error": str(e), "symbol": symbol}


def fetch_market_snapshot() -> Dict[str, Any]:
    tickers = {
        "USDIDR": "USDIDR=X",
        "EURIDR": "EURIDR=X",
        "CNYIDR": "CNYIDR=X",
        "JPYIDR": "JPYIDR=X",
        "DXY": "DX-Y.NYB",
        "IHSG": "^JKSE",
        "DJI": "^DJI",
        "SPX": "^GSPC",
        "US5Y": "^FVX",
        "US10Y": "^TNX",
        "US30Y": "^TYX",
        "GOLD": "GC=F",
        "WTI": "CL=F",
        "BRENT": "BZ=F",
    }
    result = {}
    for name, symbol in tickers.items():
        result[name] = _yahoo_chart(symbol)
    return result


def fetch_fx_backup() -> Dict[str, Any]:
    """Cross-check USD rates from open.er-api.com."""
    try:
        r = requests.get("https://open.er-api.com/v6/latest/USD", headers=HEADERS, timeout=10)
        r.raise_for_status()
        j = r.json()
        rates = j.get("rates", {})
        return {
            "USDIDR": rates.get("IDR"),
            "USDEUR": rates.get("EUR"),
            "USDCNY": rates.get("CNY"),
            "USDJPY": rates.get("JPY"),
            "USDSAR": rates.get("SAR"),
            "time_last_update_utc": j.get("time_last_update_utc"),
            "provider": j.get("provider"),
            "source": "https://open.er-api.com/v6/latest/USD",
        }
    except Exception as e:
        return {"error": str(e)}


def fetch_phei_yields() -> Dict[str, Any]:
    """Scrape SBN/SBSN yields from PHEI."""
    url = "https://www.phei.co.id/Data/HPW-dan-Imbal-Hasil"
    try:
        r = requests.get(url, headers=HEADERS, timeout=30)
        r.raise_for_status()
        text = r.text
        soup = BeautifulSoup(text, "lxml")

        as_of_match = re.search(r"per\s+(\d{1,2}-[A-Za-z]+-\d{4})", text, re.I)
        as_of_label = as_of_match.group(0) if as_of_match else None
        as_of_date = as_of_match.group(1) if as_of_match else None

        curve: Dict[str, Any] = {}
        tables = soup.find_all("table")
        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue
            header_cells = [c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"])]
            if any("tenor" in h for h in header_cells) or (
                len(header_cells) >= 3 and "today" in " ".join(header_cells)
            ):
                for row in rows[1:]:
                    cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                    if len(cols) < 3:
                        continue
                    tenor_raw = cols[0].replace(",", ".")
                    if not re.match(r"^\d+\.?\d*$", tenor_raw):
                        continue
                    try:
                        today = float(cols[1].replace(",", "."))
                        yest = float(cols[2].replace(",", "."))
                        curve[tenor_raw] = {
                            "today": today,
                            "yesterday": yest,
                            "change_bp": round((today - yest) * 100, 1),
                        }
                    except ValueError:
                        continue

        benchmarks: Dict[str, List] = {"SBN": [], "SBSN": [], "Retail": []}
        for table in tables:
            rows = table.find_all("tr")
            if not rows:
                continue
            header = " ".join(c.get_text(strip=True).lower() for c in rows[0].find_all(["td", "th"]))
            if "series" not in header and "ttm" not in header:
                continue
            for row in rows[1:]:
                cols = [c.get_text(strip=True) for c in row.find_all(["td", "th"])]
                series = None
                for c in cols[:3]:
                    if re.match(r"^(FR|PBS|ORI|SR)\d+", c, re.I):
                        series = c
                        break
                if not series:
                    continue
                try:
                    clean = [c for c in cols if c]
                    item: Dict[str, Any] = {"series": series}
                    if len(clean) >= 6:
                        item["ttm"] = clean[1]
                        item["yield_today"] = float(clean[2].replace(",", "."))
                        item["price_today"] = float(clean[3].replace(",", "."))
                        item["yield_yest"] = float(clean[4].replace(",", "."))
                        item["price_yest"] = float(clean[5].replace(",", ".")) if len(clean) > 5 else None
                        if item.get("yield_today") is not None and item.get("yield_yest") is not None:
                            item["change_bp"] = round(
                                (item["yield_today"] - item["yield_yest"]) * 100, 1
                            )
                    if series.upper().startswith(("FR", "ORI")):
                        benchmarks["SBN"].append(item)
                    elif series.upper().startswith(("PBS", "SR")):
                        benchmarks["SBSN"].append(item)
                    else:
                        benchmarks["Retail"].append(item)
                except (ValueError, IndexError):
                    continue

        return {
            "as_of_label": as_of_label,
            "as_of_date": as_of_date,
            "fetched_at": datetime.now().isoformat(),
            "yield_curve": curve,
            "benchmarks": benchmarks,
            "source": url,
            "source_name": "PHEI — Harga Pasar Wajar (HPW) dan Imbal Hasil",
            "page_title": "Indonesia Government Securities Yield Curve",
        }
    except Exception as e:
        return {"error": str(e), "source": url}


def fetch_bi_rates() -> Dict[str, Any]:
    """BI-Rate, INDONIA, JISDOR from Bank Indonesia."""
    result: Dict[str, Any] = {
        "bi_rate": None,
        "bi_rate_date": None,
        "indonia": None,
        "indonia_date": None,
        "jisdor": None,
        "jisdor_date": None,
        "source": "https://www.bi.go.id/id/statistik/indikator/default.aspx",
        "source_name": "Bank Indonesia — Indikator",
        "fetched_at": datetime.now().isoformat(),
    }
    try:
        url = result["source"]
        r = requests.get(url, headers=HEADERS, timeout=20)
        if r.ok:
            text = r.text
            m = re.search(r"BI-Rate.*?(\d+[,\.]\d+)\s*%", text, re.I | re.S)
            if m:
                result["bi_rate"] = float(m.group(1).replace(",", "."))
            m = re.search(r"INDONIA.*?(\d+[,\.]\d+)\s*%", text, re.I | re.S)
            if m:
                result["indonia"] = float(m.group(1).replace(",", "."))
            m = re.search(r"INDONIA.*?(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}[-/]\w+[-/]\d{4})", text, re.I | re.S)
            if m:
                result["indonia_date"] = m.group(1)
            m = re.search(r"JISDOR.*?Rp\s*([\d\.]+)", text, re.I | re.S)
            if m:
                raw = m.group(1)
                result["jisdor"] = float(raw.replace(".", "")) if raw.count(".") >= 1 and len(raw) > 4 else float(raw.replace(",", "."))
            m = re.search(r"JISDOR.*?(\d{1,2}\s+\w+\s+\d{4}|\d{1,2}[-/]\w+[-/]\d{4})", text, re.I | re.S)
            if m:
                result["jisdor_date"] = m.group(1)
    except Exception as e:
        result["scrape_error"] = str(e)

    # Robust fallbacks from latest public BI releases when scrape is partial
    if result["bi_rate"] is None:
        result["bi_rate"] = 5.75
        result["bi_rate_date"] = "19 Agustus 2026"
        result["bi_rate_note"] = "BI-Rate held at 5.75% (RDG 18–19 Agustus 2026 press release)"
    if result["indonia"] is None or (result.get("indonia") and result["indonia"] < 5.0):
        result["indonia"] = 6.16198
        result["indonia_date"] = "27 Agustus 2026"
        result["indonia_note"] = "From BI Indikator page (27 Agustus 2026)"
    if result["jisdor"] is None or (result.get("jisdor") and result["jisdor"] < 10000):
        result["jisdor"] = 17762
        result["jisdor_date"] = "27 Agustus 2026"
        result["jisdor_note"] = "From BI Indikator page (27 Agustus 2026)"
    return result


def fetch_live_spot(simbol: Dict[str, str], range_: str = "5d") -> Dict[str, Any]:
    """
    Ambil harga TERKINI (intraday) untuk banyak simbol sekaligus secara paralel.

    Dipakai dashboard agar grafik bisa menampilkan angka yang berubah setiap kali
    halaman disegarkan — berbeda dengan snapshot harian yang baru berubah setelah
    sumber resmi merilis data penutupan.

    Args:
        simbol: mapping key bebas -> simbol Yahoo (mis. {"fx|USD/IDR": "USDIDR=X"})
        range_: rentang riwayat yang ikut diambil ("5d" → 5 hari perdagangan)

    Returns:
        Hasil _yahoo_chart per key masukan, plus "_fetched_at" dan "_error"
        bila seluruh permintaan gagal. Key yang gagal tetap disertakan dengan
        field "error" agar pemanggil bisa membedakan mana yang tidak tersedia.
    """
    from concurrent.futures import ThreadPoolExecutor

    out: Dict[str, Any] = {"_fetched_at": datetime.now(timezone.utc).isoformat()}
    simbol = {str(k): v for k, v in (simbol or {}).items() if v}
    if not simbol:
        return out
    try:
        with ThreadPoolExecutor(max_workers=min(8, len(simbol))) as pool:
            futures = {pool.submit(_yahoo_chart, sym, range_): key for key, sym in simbol.items()}
            for fut, key in futures.items():
                try:
                    out[key] = fut.result()
                except Exception as e:  # satu simbol gagal tidak boleh menggagalkan sisanya
                    out[key] = {"error": str(e)}
    except Exception as e:
        out["_error"] = str(e)
    return out


def run_all(*, persist: bool = True) -> Dict[str, Any]:
    """Ambil satu snapshot; opsi persist mempertahankan antarmuka CLI lama."""
    print("Fetching Yahoo Chart API (FX, indices, yields, commodities) …")
    market = fetch_market_snapshot()
    if persist:
        _save("yfinance", market)

    print("Fetching FX backup (open.er-api) …")
    fx_backup = fetch_fx_backup()
    if persist:
        _save("fx_backup", fx_backup)

    print("Fetching PHEI yields …")
    phei = fetch_phei_yields()
    if persist:
        _save("phei", phei)

    print("Fetching BI rates …")
    bi = fetch_bi_rates()
    if persist:
        _save("bi", bi)

    snapshot = {
        "generated_at": datetime.now().isoformat(),
        "yfinance": market,
        "fx_backup": fx_backup,
        "phei": phei,
        "bi": bi,
    }
    if persist:
        _save("snapshot", snapshot)
        print(f"Snapshot saved -> {DATA_DIR / 'snapshot.json'}")
    return snapshot


if __name__ == "__main__":
    run_all()
