"""
Calculate daily changes from REAL snapshot. Produce report_data + sources metadata.
"""

from __future__ import annotations
import json
import os
import re
import tempfile
from datetime import datetime
import math
from pathlib import Path
from typing import Dict, Any, Optional

from market_report.config import market_data_directory
from market_report.domain.market_periods import period_changes, yield_ytd_bp
from market_report.domain.index_sectors import IDX_IC_SECTOR_INDEXES, IDX_SECTOR_HISTORY_SOURCE

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
                "availability_note": "Nilai turunan tersedia. Histori pembanding belum tersedia.",
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
                "mtd_pct": None,
                "rolling_1m_pct": item.get("rolling_1m_pct"),
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
    spot = yf.get("GOLD_SPOT", {})
    spot_reading = _unavailable_reading(
        "USD/troy oz",
        (spot.get("error") if isinstance(spot, dict) else None)
        or "Harga Gold Spot belum tersedia dari Trading Economics.",
    )
    if isinstance(spot, dict) and isinstance(spot.get("last"), (int, float)) \
            and not isinstance(spot.get("last"), bool) and math.isfinite(spot["last"]):
        spot_history = snap.get("_gold_spot_history")
        if not isinstance(spot_history, list):
            spot_history = spot.get("history") if isinstance(spot.get("history"), list) else []
        spot_periods = period_changes(spot_history, spot.get("date"), spot.get("last"))
        spot_prev = spot.get("prev")
        if not isinstance(spot_prev, (int, float)) or isinstance(spot_prev, bool) or not math.isfinite(spot_prev):
            daily_change = spot.get("change")
            spot_prev = spot["last"] - daily_change if isinstance(daily_change, (int, float)) else None
        prev_date = spot.get("prev_date")
        history_prev_date = spot_periods.get("prev_date")
        if not prev_date and history_prev_date and isinstance(spot_prev, (int, float)):
            history_prev = next((
                point.get("close") for point in spot_history
                if isinstance(point, dict)
                and str(point.get("date") or point.get("dates") or "")[:10] == history_prev_date
            ), None)
            if isinstance(history_prev, (int, float)) and math.isclose(
                float(history_prev), float(spot_prev), rel_tol=0, abs_tol=0.005,
            ):
                prev_date = history_prev_date
        spot_reading = {
            "today": spot["last"],
            "prev": spot_prev,
            "dtd_pct": spot.get("dtd_pct"),
            "change_pct": spot.get("dtd_pct"),
            "ytd_pct": spot_periods.get("ytd_pct"),
            "prev_date": prev_date,
            "date": spot.get("date"),
            "unit": spot.get("unit", "USD/troy oz"),
            "source": spot.get("source"),
            "source_name": spot.get("source_name", "Trading Economics"),
            "availability": spot.get("availability", "partial"),
            "availability_note": spot.get("availability_note"),
        }
    gold = {
        "Gold Spot (USD/troy oz)": spot_reading,
    }
    if "Gold (USD/oz)" in commodities:
        gold["Gold Futures COMEX (GC=F, USD/troy oz)"] = commodities["Gold (USD/oz)"]
    if "Emas Antam 1 gr (Rp)" in commodities:
        gold["Emas Antam (Rp/gram)"] = commodities["Emas Antam 1 gr (Rp)"]

    sector_index_map = tuple((key, label) for key, _, label, _ in IDX_IC_SECTOR_INDEXES)
    sector_history = snap.get("_index_sector_history", {})
    index_sectors = {}
    for source_key, label in sector_index_map:
        item = yf.get(source_key, {})
        if not isinstance(item, dict) or item.get("last") is None:
            reading = _unavailable_reading(
                "poin", (item.get("error") if isinstance(item, dict) else None)
                or f"Data indeks sektor {source_key} belum tersedia dari Yahoo Finance."
            )
            reading["source"] = item.get("source") if isinstance(item, dict) else None
            index_sectors[label] = reading
            continue

        history = sector_history.get(label) if isinstance(sector_history, dict) else None
        period_item = {**item, "history": history} if isinstance(history, list) else item
        periods = _period_data(period_item)
        index_sectors[label] = {
            "today": item["last"],
            "prev": item.get("prev"),
            "change_pct": item.get("change_pct"),
            "dtd_pct": item.get("change_pct"),
            "ytd_pct": periods.get("ytd_pct"),
            "date": item.get("date"),
            "unit": "poin indeks",
            "source": item.get("source"),
            "ytd_source": IDX_SECTOR_HISTORY_SOURCE if periods.get("ytd_pct") is not None else None,
            "availability": "available",
            **periods,
        }
    sources.append({
        "section": "IDX-IC Sectoral Indices",
        "items": [
            {
                "field": label,
                "source": reading.get("source"),
                "history_source": reading.get("ytd_source"),
                "as_of": reading.get("date"),
            }
            for label, reading in index_sectors.items()
        ],
        "primary": "Yahoo Finance Chart API (IDX-IC sector quotes)",
        "history_source": "IDX Daily Indices (official year-end close used for YtD baseline)",
        "reference": "Indonesia Stock Exchange (IDX-IC sector indices)",
        "url": IDX_SECTOR_HISTORY_SOURCE,
    })
    capital_flow = {}
    fetched_capital_flow = snap.get("capital_flow", {})
    for label in ("Saham", "Obligasi"):
        raw = fetched_capital_flow.get(label, {}) if isinstance(fetched_capital_flow, dict) else {}
        raw = raw if isinstance(raw, dict) else {}
        raw_periods = raw.get("periods", {})
        periods = {}
        for key in ("1D", "1W", "MtD", "QtD", "YtD"):
            value = raw_periods.get(key) if isinstance(raw_periods, dict) else None
            periods[key] = value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None
        history = raw.get("history", [])
        capital_flow[label] = {
            "unit": "USD juta",
            "periods": periods,
            "date": raw.get("date"),
            "availability": raw.get("availability", "unavailable") if any(value is not None for value in periods.values()) else "unavailable",
            "availability_note": raw.get("availability_note"),
            "source": raw.get("source"),
            "source_url": raw.get("source_url"),
            "history": history if isinstance(history, list) else [],
        }
        sources.append({
            "section": f"Capital Flow — {label}",
            "primary": raw.get("source"),
            "url": raw.get("source_url"),
            "as_of_date": raw.get("date"),
            "availability": capital_flow[label]["availability"],
            "note": raw.get("availability_note"),
        })
    macro_indicators = {
        "FED Fund Rate (%)": {"unit": "%", "observations": {}, "availability": "unavailable"},
        "BI Rate (%)": {"unit": "%", "observations": {}, "availability": "unavailable"},
        "Inflasi Indonesia YoY (%)": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
        "M2 (% YoY)": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
        "Kredit/Pembiayaan (% YoY) - BI": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
        "DPK (% YoY) - BI": {"unit": "% YoY", "observations": {}, "availability": "unavailable"},
    }
    fetched_macro = snap.get("macro_indicators", {})
    for label, reading in macro_indicators.items():
        source_reading = fetched_macro.get(label, {}) if isinstance(fetched_macro, dict) else {}
        if not isinstance(source_reading, dict):
            continue
        raw_observations = source_reading.get("observations", {})
        if isinstance(raw_observations, dict):
            reading["observations"] = {
                str(month): value for month, value in raw_observations.items()
                if re.fullmatch(r"20\d{2}-(0[1-9]|1[0-2])", str(month))
                and isinstance(value, (int, float)) and math.isfinite(value)
            }
        reading["availability"] = (
            "available" if reading["observations"] else
            source_reading.get("availability", "unavailable")
        )
        reading["source"] = source_reading.get("source")
        reading["source_name"] = source_reading.get("source_name")
        if source_reading.get("error"):
            reading["availability_note"] = source_reading["error"]

    macro_sources = [
        {
            "field": label,
            "source": reading.get("source"),
            "source_name": reading.get("source_name"),
            "as_of": max(reading.get("observations", {}), default=None),
        }
        for label, reading in macro_indicators.items()
        if reading.get("observations")
    ]
    if macro_sources:
        sources.append({"section": "Macro Indicators", "items": macro_sources})

    bi_rate_month = _month_key(bi.get("bi_rate_date"))
    if not macro_indicators["BI Rate (%)"]["observations"] and bi_rate_month and isinstance(bi.get("bi_rate"), (int, float)):
        macro_indicators["BI Rate (%)"]["observations"][bi_rate_month] = bi["bi_rate"]
        macro_indicators["BI Rate (%)"]["availability"] = "partial"
    om_source = snap.get("monetary_operations", {})
    om_source = om_source if isinstance(om_source, dict) else {}
    om_points: dict[str, float] = {}
    for point in om_source.get("history", []):
        if not isinstance(point, dict):
            continue
        day = _source_day(point.get("date") or point.get("dates"))
        value = point.get("close")
        if day and isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value):
            om_points[day] = float(value)
    om_history = [{"date": day, "close": value} for day, value in sorted(om_points.items())]
    om_latest = om_history[-1] if om_history else None
    monetary_operations = {"Posisi OM BI (Rp T)": {
        **_unavailable_reading(
            "Rp triliun",
            om_source.get("error") or "Data posisi Operasi Moneter belum tersedia dari SEKI BI.",
        ),
        "mtd_pct": None,
        "ytd_pct": None,
        "source": om_source.get("source"),
        "source_name": om_source.get("source_name"),
    }}
    if om_latest:
        om_periods = period_changes(om_history, om_latest["date"], om_latest["close"])
        previous = om_history[-2] if len(om_history) > 1 else None
        monetary_operations["Posisi OM BI (Rp T)"] = {
            "today": om_latest["close"],
            "prev": previous["close"] if previous else None,
            "prev_date": previous["date"] if previous else None,
            "mtd_pct": om_periods.get("mtd_pct"),
            "ytd_pct": om_periods.get("ytd_pct"),
            "date": om_latest["date"],
            "unit": om_source.get("unit", "Rp triliun"),
            "availability": om_source.get("availability", "available"),
            "availability_note": om_source.get("availability_note"),
            "source": om_source.get("source"),
            "source_name": om_source.get("source_name"),
        }
    sources.append({
        "section": "Monetary Operations",
        "items": [{
            "field": "Posisi OM BI (Rp T)",
            "source": om_source.get("source"),
            "source_name": om_source.get("source_name"),
            "as_of": om_latest.get("date") if om_latest else None,
            "availability": om_source.get("availability", "unavailable"),
        }],
        "note": om_source.get("availability_note") or om_source.get("error"),
    })
    sources.append({
        "section": "Commodities",
        "items": [
            {"field": k, "source": v.get("source"), "as_of": v.get("date")}
            for k, v in commodities.items()
        ],
        "primary": "Yahoo Finance Chart API — GC=F, CL=F, BZ=F",
    })
    sources.append({
        "section": "Gold Spot",
        "primary": spot.get("source_name", "Trading Economics") if isinstance(spot, dict) else "Trading Economics",
        "url": spot.get("source") if isinstance(spot, dict) else None,
        "as_of_date": spot.get("date") if isinstance(spot, dict) else None,
        "availability": spot.get("availability", "unavailable") if isinstance(spot, dict) else "unavailable",
        "note": spot.get("availability_note") or spot.get("error") if isinstance(spot, dict) else None,
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
