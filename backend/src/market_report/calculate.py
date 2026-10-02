"""
Calculate daily changes from REAL snapshot. Produce report_data + sources metadata.
"""

from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, Optional

from market_report.config import market_data_directory

DATA_DIR = market_data_directory()


def load_snapshot() -> Dict[str, Any]:
    path = DATA_DIR / "snapshot.json"
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def _g(d: dict, *keys, default=None):
    for k in keys:
        if isinstance(d, dict) and k in d:
            d = d[k]
        else:
            return default
    return d


def build_report_data(snap: Optional[Dict] = None) -> Dict[str, Any]:
    if snap is None:
        snap = load_snapshot()

    yf = snap.get("yfinance", {})
    phei = snap.get("phei", {})
    bi = snap.get("bi", {})
    fx_backup = snap.get("fx_backup", {})

    sources = []

    # ---------- FX ----------
    fx = {}
    fx_map = [
        ("DXY", "DXY", 2),
        ("USDIDR", "USD/IDR", 0),
        ("CNYIDR", "CNY/IDR", 3),
        ("EURIDR", "EUR/IDR", 0),
        ("JPYIDR", "JPY/IDR", 2),
    ]
    for key, label, _dec in fx_map:
        item = yf.get(key, {})
        if item.get("last") is not None:
            fx[label] = {
                "today": item["last"],
                "prev": item.get("prev"),
                "change_pct": item.get("change_pct"),
                "date": item.get("date"),
                "source": item.get("source"),
            }
    # SAR from backup if available
    if fx_backup.get("USDSAR") and fx.get("USD/IDR"):
        # approximate SAR/IDR = USDIDR / USDSAR
        try:
            sar_idr = fx["USD/IDR"]["today"] / fx_backup["USDSAR"]
            fx["SAR/IDR"] = {
                "today": round(sar_idr, 3),
                "prev": None,
                "change_pct": None,
                "date": fx_backup.get("time_last_update_utc"),
                "source": "Derived from open.er-api.com (USD/IDR ÷ USD/SAR)",
            }
        except Exception:
            pass

    sources.append({
        "section": "Exchange Rate",
        "items": [
            {"field": k, "source": v.get("source"), "as_of": v.get("date")}
            for k, v in fx.items()
        ],
        "primary": "Yahoo Finance Chart API (query1.finance.yahoo.com/v8/finance/chart)",
        "backup": fx_backup.get("source"),
        "backup_as_of": fx_backup.get("time_last_update_utc"),
    })

    # ---------- Indices ----------
    indices = {}
    for key, label in [("IHSG", "IHSG (ID)"), ("DJI", "DJI (US)")]:
        item = yf.get(key, {})
        if item.get("last") is not None:
            indices[label] = {
                "today": item["last"],
                "prev": item.get("prev"),
                "change_pct": item.get("change_pct"),
                "date": item.get("date"),
                "source": item.get("source"),
            }
    sources.append({
        "section": "Financial Market (Indices)",
        "items": [
            {"field": k, "source": v.get("source"), "as_of": v.get("date")}
            for k, v in indices.items()
        ],
        "primary": "Yahoo Finance Chart API — ^JKSE (IHSG), ^DJI",
    })

    # ---------- Yields ----------
    yields = {}
    for key, label in [("US5Y", "US Treasury 5 Tahun"), ("US10Y", "US Treasury 10 Tahun")]:
        item = yf.get(key, {})
        if item.get("last") is not None:
            yields[label] = {
                "today": item["last"],
                "prev": item.get("prev"),
                "change_bp": round((item["last"] - item["prev"]) * 100, 1) if item.get("prev") else None,
                "date": item.get("date"),
                "source": item.get("source"),
            }

    curve = phei.get("yield_curve", {})
    for tenor_key, label in [("5.0", "ID SBN 5 Tahun"), ("5", "ID SBN 5 Tahun"),
                              ("10.0", "ID SBN 10 Tahun"), ("10", "ID SBN 10 Tahun")]:
        if tenor_key in curve and label not in yields:
            c = curve[tenor_key]
            yields[label] = {
                "today": c["today"],
                "prev": c["yesterday"],
                "change_bp": c.get("change_bp"),
                "date": phei.get("as_of_date"),
                "source": phei.get("source_name"),
                "as_of_label": phei.get("as_of_label"),
            }

    for b in phei.get("benchmarks", {}).get("SBSN", []):
        series = b.get("series", "")
        if "PBS040" in series:
            yields["ID SBSN 4 Tahun Benchmark (PBS040)"] = {
                "today": b.get("yield_today"),
                "prev": b.get("yield_yest"),
                "change_bp": b.get("change_bp"),
                "date": phei.get("as_of_date"),
                "source": phei.get("source_name"),
                "as_of_label": phei.get("as_of_label"),
                "series": series,
                "ttm": b.get("ttm"),
            }
        if "PBS034" in series:
            yields["ID SBSN 13 Tahun Benchmark (PBS034)"] = {
                "today": b.get("yield_today"),
                "prev": b.get("yield_yest"),
                "change_bp": b.get("change_bp"),
                "date": phei.get("as_of_date"),
                "source": phei.get("source_name"),
                "as_of_label": phei.get("as_of_label"),
                "series": series,
                "ttm": b.get("ttm"),
            }

    # SBN Benchmark Series — FR0109 (~5Y) & FR0108 (~10Y)
    for b in phei.get("benchmarks", {}).get("SBN", []):
        series = b.get("series", "")
        if series == "FR0109":
            yields["ID SBN FR0109 (~5Y Benchmark)"] = {
                "today": b.get("yield_today"),
                "prev": b.get("yield_yest"),
                "change_bp": b.get("change_bp"),
                "date": phei.get("as_of_date"),
                "source": phei.get("source_name"),
                "as_of_label": phei.get("as_of_label"),
                "series": series,
                "ttm": b.get("ttm"),
                "price_today": b.get("price_today"),
                "price_yest": b.get("price_yest"),
            }
        if series == "FR0108":
            yields["ID SBN FR0108 (~10Y Benchmark)"] = {
                "today": b.get("yield_today"),
                "prev": b.get("yield_yest"),
                "change_bp": b.get("change_bp"),
                "date": phei.get("as_of_date"),
                "source": phei.get("source_name"),
                "as_of_label": phei.get("as_of_label"),
                "series": series,
                "ttm": b.get("ttm"),
                "price_today": b.get("price_today"),
                "price_yest": b.get("price_yest"),
            }

    sources.append({
        "section": "Yield (US Treasury)",
        "items": [
            {"field": k, "source": v.get("source"), "as_of": v.get("date")}
            for k, v in yields.items() if "US Treasury" in k
        ],
        "primary": "Yahoo Finance Chart API — ^FVX (5Y), ^TNX (10Y)",
    })
    sources.append({
        "section": "Yield (SBN / SBSN)",
        "items": [
            {
                "field": k,
                "source": v.get("source"),
                "as_of": v.get("as_of_label") or v.get("date"),
                "series": v.get("series"),
                "ttm": v.get("ttm"),
            }
            for k, v in yields.items() if "SBN" in k or "SBSN" in k
        ],
        "primary": phei.get("source_name"),
        "url": phei.get("source"),
        "as_of_label": phei.get("as_of_label"),
        "as_of_date": phei.get("as_of_date"),
        "page_title": phei.get("page_title"),
        "fetched_at": phei.get("fetched_at"),
    })

    # Spread
    sbn10 = yields.get("ID SBN 10 Tahun", {}).get("today")
    ust10 = yields.get("US Treasury 10 Tahun", {}).get("today")
    spread_bp = round((sbn10 - ust10) * 100, 0) if sbn10 is not None and ust10 is not None else None

    # ---------- BI ----------
    bi_info = {
        "BI Rate": bi.get("bi_rate"),
        "BI Rate Date": bi.get("bi_rate_date"),
        "INDONIA": bi.get("indonia"),
        "INDONIA Date": bi.get("indonia_date"),
        "JISDOR": bi.get("jisdor"),
        "JISDOR Date": bi.get("jisdor_date"),
        "note": bi.get("bi_rate_note"),
    }
    sources.append({
        "section": "BI Rate / INDONIA / JISDOR",
        "primary": bi.get("source_name"),
        "url": bi.get("source"),
        "bi_rate": bi.get("bi_rate"),
        "bi_rate_date": bi.get("bi_rate_date"),
        "indonia": bi.get("indonia"),
        "indonia_date": bi.get("indonia_date"),
        "jisdor": bi.get("jisdor"),
        "jisdor_date": bi.get("jisdor_date"),
        "note": bi.get("bi_rate_note"),
        "fetched_at": bi.get("fetched_at"),
    })

    # ---------- Commodities ----------
    commodities = {}
    for key, label in [("GOLD", "Gold (USD/oz)"), ("WTI", "WTI Crude"), ("BRENT", "Brent Crude")]:
        item = yf.get(key, {})
        if item.get("last") is not None:
            commodities[label] = {
                "today": item["last"],
                "prev": item.get("prev"),
                "change_pct": item.get("change_pct"),
                "date": item.get("date"),
                "source": item.get("source"),
            }
    sources.append({
        "section": "Commodities",
        "items": [
            {"field": k, "source": v.get("source"), "as_of": v.get("date")}
            for k, v in commodities.items()
        ],
        "primary": "Yahoo Finance Chart API — GC=F, CL=F, BZ=F",
    })

    # History for rate differential chart
    hist_ust = _g(yf, "US10Y", "history") or []
    hist_sbn_curve = curve  # only point-in-time from PHEI

    report = {
        "schema_version": 1,
        "report_date": datetime.now().strftime("%d %B %Y"),
        "report_date_iso": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "fx": fx,
        "indices": indices,
        "yields": yields,
        "spread_sbn10_ust10_bp": spread_bp,
        "bi": bi_info,
        "commodities": commodities,
        "sources": sources,
        "phei_meta": {
            "as_of_label": phei.get("as_of_label"),
            "as_of_date": phei.get("as_of_date"),
            "url": phei.get("source"),
            "source_name": phei.get("source_name"),
        },
        "history_ust10": hist_ust,
        "source_snapshot": snap.get("generated_at"),
        "is_demo": False,
    }
    return report


def persist_json_data(data: Any, path: Path) -> None:
    """Simpan JSON secara atomik di direktori tujuan."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary_path = tempfile.mkstemp(prefix=f"{path.stem}_", suffix=".tmp", dir=path.parent)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as output:
            json.dump(data, output, ensure_ascii=False, indent=2, default=str)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary_path, path)
    except Exception:
        try:
            os.unlink(temporary_path)
        except OSError:
            pass
        raise


def persist_report_data(report: Dict[str, Any], path: Path | None = None) -> None:
    """Simpan laporan aktif secara atomik agar file lama tetap utuh bila gagal."""
    persist_json_data(report, path or DATA_DIR / "report_data.json")


if __name__ == "__main__":
    from market_report.services.report_service import rebuild_from_saved_snapshot

    data = rebuild_from_saved_snapshot()
    print(json.dumps({k: data[k] for k in ["report_date", "fx", "indices", "yields", "spread_sbn10_ust10_bp", "bi", "phei_meta"]}, indent=2, default=str))
