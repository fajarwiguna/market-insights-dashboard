"""
Calculate daily changes from REAL snapshot. Produce report_data + sources metadata.
"""

from __future__ import annotations
import json
import os
import tempfile
from datetime import datetime
import math
from pathlib import Path
from typing import Dict, Any, Optional

from market_report.config import market_data_directory
from market_report.domain.market_periods import period_changes, yield_ytd_bp

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


def _period_data(item: dict, *, is_yield: bool = False) -> dict:
    """Build dated comparison fields from a source's own observation history."""
    values = period_changes(item.get("history"), item.get("date"), item.get("last"))
    if is_yield:
        values["ytd_bp"] = yield_ytd_bp(item.get("history"), item.get("date"), item.get("last"))
    return values


def _unavailable_reading(unit: str, note: str = "Sumber data belum tersedia") -> dict:
    return {
        "today": None,
        "prev": None,
        "change_pct": None,
        "change_bp": None,
        "ytd_pct": None,
        "ytd_bp": None,
        "date": None,
        "unit": unit,
        "availability": "unavailable",
        "availability_note": note,
    }


def _month_key(value: Any) -> str | None:
    """Normalize the Indonesian/English source date into a YYYY-MM key."""
    if not value:
        return None
    raw = str(value).strip()
    try:
        return datetime.fromisoformat(raw[:10]).strftime("%Y-%m")
    except ValueError:
        pass
    try:
        from market_report.services.history_service import source_date_iso

        normalized = source_date_iso(raw)
        return normalized[:7] if normalized else None
    except (ValueError, TypeError):
        return None


def _source_day(value: Any) -> str | None:
    if not value:
        return None
    raw = str(value)
    try:
        return datetime.fromisoformat(raw[:10]).strftime("%Y-%m-%d")
    except ValueError:
        from market_report.services.history_service import source_date_iso

        return source_date_iso(raw)


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
                "dtd_pct": item.get("change_pct"),
                "change_pct": item.get("change_pct"),
                "date": item.get("date"),
                "unit": {
                    "DXY": "indeks",
                    "USD/IDR": "IDR/USD",
                    "CNY/IDR": "IDR/CNY",
                    "EUR/IDR": "IDR/EUR",
                    "JPY/IDR": "IDR/JPY",
                }.get(label),
                "source": item.get("source"),
                **_period_data(item),
            }
    # SAR from backup if available
    if fx_backup.get("USDSAR") and fx.get("USD/IDR"):
        # approximate SAR/IDR = USDIDR / USDSAR
        try:
            sar_idr = fx["USD/IDR"]["today"] / fx_backup["USDSAR"]
            fx["SAR/IDR"] = {
                "today": round(sar_idr, 3),
                "prev": None,
                "dtd_pct": None,
                "change_pct": None,
                "ytd_pct": None,
                "date": fx_backup.get("time_last_update_utc"),
                "unit": "IDR/SAR",
                "availability": "partial",
                "availability_note": "Nilai turunan tersedia; histori pembanding belum tersedia.",
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
                "dtd_pct": item.get("change_pct"),
                "change_pct": item.get("change_pct"),
                "date": item.get("date"),
                "unit": "poin indeks",
                "source": item.get("source"),
                **_period_data(item),
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
                "dtd_bp": round((item["last"] - item["prev"]) * 100, 1) if item.get("prev") else None,
                "date": item.get("date"),
                "unit": "%",
                "source": item.get("source"),
                **_period_data(item, is_yield=True),
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
                "dtd_bp": c.get("change_bp"),
                "ytd_bp": None,
                "date": phei.get("as_of_date"),
                "unit": "%",
                "source": phei.get("source_name"),
                "as_of_label": phei.get("as_of_label"),
            }

    for b in phei.get("benchmarks", {}).get("SBSN", []):
        series = str(b.get("series") or "").upper()
        if not series.startswith("PBS"):
            continue
        ttm_raw = b.get("ttm")
        try:
            ttm = float(str(ttm_raw).replace(",", "."))
        except (TypeError, ValueError):
            ttm = None
        tenor_label = f" (TTM {ttm:g}Y)" if ttm is not None else ""
        label = f"ID SBSN {series}{tenor_label}"
        yields[label] = {
            "today": b.get("yield_today"),
            "prev": b.get("yield_yest"),
            "change_bp": b.get("change_bp"),
            "dtd_bp": b.get("change_bp"),
            "ytd_bp": None,
            "date": phei.get("as_of_date"),
            "unit": "%",
            "source": phei.get("source_name"),
            "as_of_label": phei.get("as_of_label"),
            "series": series,
            "ttm": ttm,
        }

    sbn_history = snap.get("_sbn_history") or []
    sbn10 = yields.get("ID SBN 10 Tahun")
    if isinstance(sbn10, dict):
        sbn_day = _source_day(sbn10.get("date"))
        sbn10["ytd_bp"] = yield_ytd_bp(sbn_history, sbn_day, sbn10.get("today"))

    # SBN Benchmark Series — FR0109 (~5Y) & FR0108 (~10Y)
    for b in phei.get("benchmarks", {}).get("SBN", []):
        series = b.get("series", "")
        if series == "FR0109":
            yields["ID SBN FR0109 (~5Y Benchmark)"] = {
                "today": b.get("yield_today"),
                "prev": b.get("yield_yest"),
                "change_bp": b.get("change_bp"),
                "dtd_bp": b.get("change_bp"),
                "ytd_bp": None,
                "date": phei.get("as_of_date"),
                "unit": "%",
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
                "dtd_bp": b.get("change_bp"),
                "ytd_bp": None,
                "date": phei.get("as_of_date"),
                "unit": "%",
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
                "dtd_pct": item.get("change_pct"),
                "change_pct": item.get("change_pct"),
                "date": item.get("date"),
                "source": item.get("source"),
                "unit": "USD/troy oz (COMEX futures)" if key == "GOLD" else "USD/barrel",
                **_period_data(item),
            }
    for key, label, unit in (
        ("NEWCASTLE_COAL", "Coal (Newcastle)", "USD/ton"),
        ("CPO", "CPO (Bursa Malaysia)", "MYR/ton"),
    ):
        item = yf.get(key, {})
        if isinstance(item.get("last"), (int, float)) and math.isfinite(item["last"]):
            commodities[label] = {
                "today": item["last"],
                "prev": None,
                "dtd_pct": item.get("dtd_pct"),
                "change_pct": item.get("dtd_pct"),
                "wtd_pct": None,
                "mtd_pct": item.get("mtd_pct"),
                "ytd_pct": None,
                "date": item.get("date"),
                "source": item.get("source"),
                "source_name": item.get("source_name"),
                "availability": item.get("availability", "partial"),
                "availability_note": item.get("availability_note"),
                "unit": unit,
            }
    antam = snap.get("antam_gold", {})
    if isinstance(antam, dict) and antam.get("price") is not None:
        antam_series = antam.get("series_id") or "ocebsi_antam_buy_1g"
        saved_antam_history = snap.get("_antam_gold_history")
        antam_history = [
            point for point in saved_antam_history if isinstance(point, dict)
            and (point.get("series_id") or "legacy_antam") == antam_series
        ] if isinstance(saved_antam_history, list) else []
        antam_periods = period_changes(
            antam_history, antam.get("date"), antam.get("price")
        )
        commodities["Emas Antam 1 gr (Rp)"] = {
            "today": antam.get("price"),
            "prev": antam.get("prev"),
            "dtd_pct": antam.get("change_pct"),
            "change_pct": antam.get("change_pct"),
            "date": antam.get("date"),
            "source": antam.get("source"),
            "unit": "Rp/gram",
            "series_id": antam_series,
            "availability": antam.get("availability", "available"),
            "availability_note": antam.get("availability_note"),
            **antam_periods,
            "price_with_tax": antam.get("price_with_tax"),
            "basis": antam.get("basis"),
        }

    # Keep rows visible and show the feed error if a connected commodity source fails.
    for key, unit, label in (
        ("NEWCASTLE_COAL", "USD/ton", "Coal (Newcastle)"),
        ("CPO", "MYR/ton", "CPO (Bursa Malaysia)"),
    ):
        item = yf.get(key, {})
        if label not in commodities:
            note = item.get("error") or "Harga belum tersedia dari feed yang terhubung."
            commodities[label] = _unavailable_reading(unit, note)
    commodities.setdefault("Gold Spot (USD/troy oz)", _unavailable_reading("USD/troy oz", "Feed spot belum tersedia; GC=F adalah futures."))

    gold = {
        "Gold Spot (USD/troy oz)": commodities["Gold Spot (USD/troy oz)"],
    }
    if "Gold (USD/oz)" in commodities:
        gold["Gold Futures COMEX (GC=F, USD/troy oz)"] = commodities["Gold (USD/oz)"]
    if "Emas Antam 1 gr (Rp)" in commodities:
        gold["Emas Antam (Rp/gram)"] = commodities["Emas Antam 1 gr (Rp)"]

    index_sectors = {
        name: _unavailable_reading("poin", "Seri indeks sektor IDX-IC belum terhubung ke sumber data.")
        for name in (
            "Energi", "Bahan Baku", "Industri", "Konsumen Siklikal",
            "Konsumen Non-Siklikal", "Kesehatan", "Keuangan", "Properti",
            "Teknologi", "Infrastruktur", "Transportasi dan Logistik",
        )
    }
    capital_flow = {
        "Saham": {"unit": "USD juta", "periods": {key: None for key in ("1D", "1W", "MtD", "QtD", "YtD")}, "availability": "unavailable"},
        "Obligasi": {"unit": "USD juta", "periods": {key: None for key in ("1D", "1W", "MtD", "QtD", "YtD")}, "availability": "unavailable"},
    }
    macro_indicators = {
        "FED Fund Rate (%)": {"unit": "%", "observations": {}, "availability": "unavailable"},
        "BI Rate (%)": {"unit": "%", "observations": {}, "availability": "unavailable"},
        "Inflasi Indonesia YoY (%)": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
        "M2 (% YoY)": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
        "Kredit/Pembiayaan (% YoY) - BI": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
        "DPK (% YoY) - BI": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
    }
    bi_rate_month = _month_key(bi.get("bi_rate_date"))
    if bi_rate_month and isinstance(bi.get("bi_rate"), (int, float)):
        macro_indicators["BI Rate (%)"]["observations"][bi_rate_month] = bi["bi_rate"]
        macro_indicators["BI Rate (%)"]["availability"] = "partial"
    monetary_operations = {
        "Posisi OM BI (Rp T)": {
            **_unavailable_reading("Rp triliun", "Seri posisi operasi moneter BI belum terhubung."),
            "mtd_pct": None,
        }
    }
    sources.append({
        "section": "Commodities",
        "items": [
            {"field": k, "source": v.get("source"), "as_of": v.get("date")}
            for k, v in commodities.items()
        ],
        "primary": "Yahoo Finance Chart API — GC=F, CL=F, BZ=F",
    })

    sources.append({
        "section": "Emas Antam",
        "primary": antam.get("source_name", "OCEBSI ANTAM") if isinstance(antam, dict) else "OCEBSI ANTAM",
        "url": antam.get("source") if isinstance(antam, dict) else None,
        "series_id": antam.get("series_id") if isinstance(antam, dict) else None,
        "availability": antam.get("availability") if isinstance(antam, dict) else None,
        "as_of_label": antam.get("date") if isinstance(antam, dict) else None,
        "as_of_date": antam.get("date") if isinstance(antam, dict) else None,
        "fetched_at": antam.get("fetched_at") if isinstance(antam, dict) else None,
        "note": antam.get("basis", "Harga dasar emas batangan Antam 1 gram.") if isinstance(antam, dict) else "Harga dasar emas batangan Antam 1 gram.",
    })

    # History for rate differential chart
    hist_ust = _g(yf, "US10Y", "history") or []
    hist_sbn_curve = curve  # only point-in-time from PHEI

    report = {
        "schema_version": 2,
        "report_date": datetime.now().strftime("%d %B %Y"),
        "report_date_iso": datetime.now().strftime("%Y-%m-%d"),
        "generated_at": datetime.now().isoformat(),
        "fx": fx,
        "indices": indices,
        "index_sectors": index_sectors,
        "yields": yields,
        "spread_sbn10_ust10_bp": spread_bp,
        "bi": bi_info,
        "macro_indicators": macro_indicators,
        "capital_flow": capital_flow,
        "monetary_operations": monetary_operations,
        "gold": gold,
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
