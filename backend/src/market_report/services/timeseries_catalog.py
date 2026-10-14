"""Katalog resmi series time-series yang ditarik pipeline harian.

Modul ini satu-satunya acuan untuk:
1. nama tabel kanonis `{cakupan}_{Subjek}_{sumber}_{frekuensi}`,
2. nama kolom series `{wilayah}_{indikator}_{rincian}`,
3. identitas `series_id` = nama tabel tanpa underscore + `_` + nama series
   tanpa underscore (dipakai `meta_timeseries.id`),
4. ekstraksi observasi bertanggal dari snapshot laporan.

Penamaan mengikuti `panduan_penamaan.md` versi 2.0: cakupan dan sumber
lowercase dari registry, Subjek PascalCase tanpa underscore tambahan,
frekuensi satu huruf, total tepat empat komponen.
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# A. Registry penamaan (panduan_penamaan.md §2)
# ---------------------------------------------------------------------------

# §2.1 Kode cakupan (lowercase, wajib terdaftar di sini).
SCOPES = ("glob", "natl", "prov", "reg", "muni", "meta")
SCOPE_VALUES = frozenset(SCOPES)

# §2.3 Kode frekuensi (grain observasi, bukan jadwal job).
FREQUENCIES = ("d", "w", "m", "q", "y")

# Kode sumber ringkas satu kata (tanpa underscore) yang dipakai di nama tabel,
# dipetakan ke nama penerbit data. Panduan §8 menetapkan kolom `source` pada
# `meta_table`/`meta_timeseries` diisi penerbit, mis. "Bank Indonesia",
# sedangkan nama tabel tetap memakai kode ringkas (mis. `bi`).
#
# Hanya sumber yang benar-benar diambil pipeline; `bbg`/`ceic`/`xls`/`web`
# tidak pernah dipakai karena tidak ada akuisisi dari Bloomberg/CEIC.
SOURCE_NAMES: dict[str, str] = {
    "bi": "Bank Indonesia",
    "te": "Trading Economics",
    "yahoo": "Yahoo Finance",
    "erapi": "open.er-api.com",
    "antam": "Antam",
    "phei": "PHEI",
    "idx": "IDX",
    "djppr": "DJPPR",
    "fred": "FRED",
    "safe": "SAFE",
    "moj": "MOF Japan",
    "bm": "Bursa Malaysia",
}
SOURCE_CODES = frozenset(SOURCE_NAMES)


def source_name(code: str) -> str:
    """Nama penerbit untuk kolom `source`; nama kode bila tidak terdaftar."""
    return SOURCE_NAMES.get(code, code)

DEFAULT_TYPE = "NUMERIC(19,6)"
DATE_TYPE = "DATE"

# ---------------------------------------------------------------------------
# B. Judul tabel & tipe (meta_table.table_title / table_type)
# ---------------------------------------------------------------------------

TABLE_META = {
    "glob_FinancialMarket_yahoo_d": ("Global Financial Market (Yahoo Finance)", "observation"),
    "glob_Monetary_yahoo_d": ("Global Monetary - FX (Yahoo Finance)", "observation"),
    "glob_Commodity_yahoo_d": ("Global Commodity (Yahoo Finance)", "observation"),
    "natl_FinancialMarket_yahoo_d": ("Indonesia Financial Market (Yahoo Finance)", "observation"),
    "natl_StockFlow_idx_d": ("Indonesia Equity Net Foreign Flow (IDX)", "observation"),
    "natl_BondFlow_djppr_d": ("Indonesia Bond Net Foreign Flow (DJPPR)", "observation"),
    "meta_date_idx_d": ("IDX Business Dates Calendar", "reference"),
    "glob_Commodity_te_d": ("Global Commodity (Trading Economics)", "observation"),
    "glob_Rates_te_d": ("Global Policy Rates (Trading Economics)", "observation"),
    "glob_Monetary_erapi_d": ("Global Monetary - Backup Rate (er-api)", "observation"),
    "natl_Macro_te_m": ("Indonesia Macro (Trading Economics)", "observation"),
    "natl_Commodity_antam_d": ("Indonesia Gold Price ANTAM", "observation"),
    "natl_SbnYield_phei_d": ("Indonesia Government Bond Yield (PHEI)", "observation"),
    "natl_Rates_bi_d": ("Indonesia Policy Rates (Bank Indonesia)", "observation"),
    "natl_Monetary_bi_m": ("Indonesia Monetary Operations (Bank Indonesia)", "observation"),
    "natl_Macro_bi_m": ("Indonesia Macro Credit & Deposit (Bank Indonesia)", "observation"),
    "glob_EquityFlow_safe_m": ("China Inbound Equity Flow (SAFE)", "observation"),
    "glob_EquityFlow_moj_m": ("Japan Inbound Equity Flow (MOF Japan)", "observation"),
    "glob_EquityFlow_bm_m": ("Malaysia Inbound Equity Flow (Bursa Malaysia)", "observation"),
    "glob_EquityFlow_fred_m": ("US Inbound Equity Flow (FRED)", "observation"),
}

ORGANIZATIONAL_ACCESS = "public"


def series_id_for(table: str, series_name: str) -> str:
    """`meta_timeseries.id` = tabel tanpa underscore + `_` + series tanpa underscore."""
    return f"{table.replace('_', '')}_{series_name.replace('_', '')}"


def _scope_of(table: str) -> str:
    return table.split("_", 1)[0]


def _frequency_of(table: str) -> str:
    return table.rsplit("_", 1)[1]


def _series(table: str, series_name: str, description: str, *, unit=None,
            data_type=None, tag="x"):
    """Satu baris `meta_timeseries` lengkap dengan identitas tabelnya."""
    code = table.split("_")[2]
    return {
        "table": table,
        "table_title": TABLE_META[table][0],
        "table_type": TABLE_META[table][1],
        "series_name": series_name,
        "series_id": series_id_for(table, series_name),
        "scope": _scope_of(table),
        "source": source_name(code),   # nama penerbit untuk kolom `source`
        "source_code": code,           # token satu kata di nama tabel
        "frequency": _frequency_of(table),
        "data_type": data_type or DEFAULT_TYPE,
        "description": description,
        "unit": unit,
        "tag": tag,
    }


# ---------------------------------------------------------------------------
# C. Katalog series pipeline
# ---------------------------------------------------------------------------

_INDEX_SECTORS = (
    ("idx_composite", "Indeks Harga Saham Gabungan (IHSG)"),
    ("idx_energy", "IDX-IC Sector Energi"),
    ("idx_basic", "IDX-IC Sector Bahan Baku"),
    ("idx_industrials", "IDX-IC Sector Industri"),
    ("idx_cyclical", "IDX-IC Sector Konsumen Non-Primer"),
    ("idx_noncyclical", "IDX-IC Sector Konsumen Primer"),
    ("idx_healthcare", "IDX-IC Sector Kesehatan"),
    ("idx_finance", "IDX-IC Sector Keuangan"),
    ("idx_property", "IDX-IC Sector Properti & Real Estate"),
    ("idx_techno", "IDX-IC Sector Teknologi"),
    ("idx_infra", "IDX-IC Sector Infrastruktur"),
    ("idx_transport", "IDX-IC Sector Transportasi & Logistik"),
)

_CATALOG_ROWS: list[dict] = []

# --- Pasar global & Indonesia (diambil via Yahoo Finance) ---
for _name, _desc in (
    ("dji_index", "Dow Jones Industrial Average"),
    ("spx_index", "S&P 500 Index"),
    ("nky_index", "Nikkei 225 Index"),
    ("hsi_index", "Hang Seng Index"),
    ("fbmklci_index", "FTSE Bursa Malaysia KLCI"),
    ("sti_index", "Straits Times Index"),
    ("us_gov_5yr", "US Treasury 5-Year Yield"),
    ("us_gov_10yr", "US Treasury 10-Year Yield"),
    ("us_gov_30yr", "US Treasury 30-Year Yield"),
):
    _unit = "%" if _name.startswith("us_gov") else "index"
    _tag = "yields" if _name.startswith("us_gov") else "indices"
    _CATALOG_ROWS.append(_series("glob_FinancialMarket_yahoo_d", _name, _desc,
                                 unit=_unit, tag=_tag))

for _name, _desc, _unit in (
    ("usd_idr", "Kurs USD/IDR", "IDR"),
    ("eur_idr", "Kurs EUR/IDR", "IDR"),
    ("cny_idr", "Kurs CNY/IDR", "IDR"),
    ("jpy_idr", "Kurs JPY/IDR", "IDR"),
    ("dollar_index", "US Dollar Index (DXY)", "index"),
):
    _CATALOG_ROWS.append(_series("glob_Monetary_yahoo_d", _name, _desc,
                                 unit=_unit, tag="fx"))

_CATALOG_ROWS.append(_series("glob_Commodity_yahoo_d", "crude_oil_brent_price",
                             "Brent Crude Oil Futures (ICE BZ)", unit="USD/bbl",
                             tag="commodities"))

for _name, _desc in _INDEX_SECTORS:
    _CATALOG_ROWS.append(_series("natl_FinancialMarket_yahoo_d", _name, _desc,
                                 unit="index", tag="indonesia_equity"))

_CATALOG_ROWS.append(_series(
    "natl_StockFlow_idx_d", "id_idx_netforeignflow_daily_idr",
    "Net foreign flow saham harian (IDX)", unit="IDR", tag="capital_flow"))
_CATALOG_ROWS.append(_series(
    "natl_BondFlow_djppr_d", "id_bond_netforeignflow_daily_idr",
    "Net foreign flow SBN harian (DJPPR)", unit="IDR", tag="capital_flow"))
_CATALOG_ROWS.append(_series(
    "meta_date_idx_d", "id_business_dates", "IDX Business Dates Calendar",
    unit="date", data_type=DATE_TYPE, tag="calendar"))

# --- Komoditas & indeks dari Yahoo Finance ---
_CATALOG_ROWS.append(_series("glob_Commodity_yahoo_d", "gold_comex_futures",
                             "Gold Futures COMEX (GC=F)", unit="USD/oz",
                             tag="commodities"))
_CATALOG_ROWS.append(_series("glob_Commodity_yahoo_d", "crude_oil_wti",
                             "WTI Crude Oil Futures (NYMEX CL)", unit="USD/bbl",
                             tag="commodities"))
_CATALOG_ROWS.append(_series("glob_FinancialMarket_yahoo_d", "nasdaq_composite",
                             "Nasdaq Composite Index", unit="index", tag="indices"))

# --- Trading Economics ---
_CATALOG_ROWS.append(_series("glob_Commodity_te_d", "gold_spot",
                             "Gold Spot (referensi OTC/CFD Trading Economics)",
                             unit="USD/oz", tag="commodities"))
_CATALOG_ROWS.append(_series("glob_Commodity_te_d", "coal_newcastle",
                             "Coal Newcastle (Trading Economics)", unit="USD/ton",
                             tag="commodities"))
_CATALOG_ROWS.append(_series("glob_Commodity_te_d", "my_cpo",
                             "CPO Bursa Malaysia (Trading Economics)",
                             unit="MYR/ton", tag="commodities"))
_CATALOG_ROWS.append(_series("glob_Rates_te_d", "us_fed_funds_rate",
                             "US Federal Funds Target Rate", unit="%",
                             tag="rates"))

_CATALOG_ROWS.append(_series("glob_Monetary_erapi_d", "usd_idr_backup",
                             "USD/IDR cadangan (open.er-api.com)", unit="IDR",
                             tag="fx"))

for _name, _desc in (
    ("id_inflation_yoy", "Inflasi Indonesia YoY"),
    ("id_m2_yoy", "M2 (% YoY)"),
):
    _CATALOG_ROWS.append(_series("natl_Macro_te_m", _name, _desc, unit="%",
                                 tag="macro"))

_CATALOG_ROWS.append(_series("natl_Commodity_antam_d", "id_gold_antam_sell_1g",
                             "Harga Jual Emas Batangan ANTAM 1 gram",
                             unit="IDR/gram", tag="commodities"))

_CATALOG_ROWS.append(_series("natl_SbnYield_phei_d", "id_sbn_5y",
                             "SBN 5-Year Yield (PHEI)", unit="%", tag="sbn"))
_CATALOG_ROWS.append(_series("natl_SbnYield_phei_d", "id_sbn_10y",
                             "SBN 10-Year Yield (PHEI)", unit="%", tag="sbn"))

for _name, _desc, _unit, _tag in (
    ("id_bi_rate", "BI-Rate (Bank Indonesia Policy Rate)", "%", "rates"),
    ("id_indonia", "INDONIA Overnight Interbank Rate", "%", "rates"),
    ("id_jisdor", "JISDOR (BI Reference Rate)", "IDR", "fx"),
):
    _CATALOG_ROWS.append(_series("natl_Rates_bi_d", _name, _desc, unit=_unit,
                                 tag=_tag))

_CATALOG_ROWS.append(_series(
    "natl_Monetary_bi_m", "id_monetary_operations",
    "Total Posisi Operasi Moneter (SEKI BI Tabel III.1)", unit="Rp triliun",
    tag="macro"))
_CATALOG_ROWS.append(_series(
    "natl_Monetary_bi_m", "id_foreign_reserves", "Cadangan Devisa (SEKI BI)",
    unit="USD mn", tag="macro"))

_CATALOG_ROWS.append(_series(
    "natl_Macro_bi_m", "id_credit_yoy", "Kredit/Pembiayaan (% YoY) - BI",
    unit="%", tag="macro"))
_CATALOG_ROWS.append(_series(
    "natl_Macro_bi_m", "id_dpk_yoy", "DPK (% YoY) - BI", unit="%", tag="macro"))

for _table, _name, _desc in (
    ("glob_EquityFlow_safe_m", "cn_inbound_equity_flow",
     "China Inbound Portfolio Equity Flow"),
    ("glob_EquityFlow_moj_m", "jp_inbound_equity_flow",
     "Japan Inbound Portfolio Equity Flow"),
    ("glob_EquityFlow_bm_m", "my_inbound_equity_flow",
     "Malaysia Inbound Portfolio Equity Flow"),
    ("glob_EquityFlow_fred_m", "us_inbound_equity_flow",
     "US Inbound Portfolio Equity Flow"),
):
    _CATALOG_ROWS.append(_series(_table, _name, _desc, unit="USD mn",
                                 tag="capital_flow"))


def _unique(rows: list[dict]) -> list[dict]:
    seen: dict[str, dict] = {}
    for row in rows:
        seen.setdefault(row["series_id"], row)
    return list(seen.values())


PIPELINE_SERIES = _unique(_CATALOG_ROWS)
SERIES_BY_ID = {row["series_id"]: row for row in PIPELINE_SERIES}

# Tabel unik yang perlu dibuat di database (diurutkan agar deterministik).
TABLES = sorted({row["table"] for row in PIPELINE_SERIES})


def table_specs() -> list[dict]:
    """Satu baris `meta_table` per tabel fisik."""
    specs = []
    for table in TABLES:
        title, table_type = TABLE_META[table]
        specs.append({
            "id": table,
            "table_name": table,
            "table_title": title,
            "scope": _scope_of(table),
            "source": source_name(table.split("_")[2]),
            "frequency": _frequency_of(table),
            "table_type": table_type,
            "organizational_access": ORGANIZATIONAL_ACCESS,
        })
    return specs


def table_columns() -> dict[str, list[dict]]:
    """Kolom tiap tabel: `{table: [{series_name, data_type, series_id}, ...]}`."""
    grouped: dict[str, list[dict]] = {}
    for row in PIPELINE_SERIES:
        grouped.setdefault(row["table"], []).append({
            "series_name": row["series_name"],
            "data_type": row["data_type"],
            "series_id": row["series_id"],
        })
    return grouped


def catalog_series_ids() -> set[str]:
    return set(SERIES_BY_ID)


def series_lookup() -> dict[str, dict]:
    """`{series_id: {table, series_name, data_type}}` untuk repository."""
    return {
        row["series_id"]: {
            "table": row["table"],
            "series_name": row["series_name"],
            "data_type": row["data_type"],
        }
        for row in PIPELINE_SERIES
    }


# ---------------------------------------------------------------------------
# D. Ekstraksi observasi dari snapshot laporan
# ---------------------------------------------------------------------------

# Instrumen yang tidak pernah diunggah walau ada di katalog.
OBSERVATION_SKIP = frozenset({
    series_id_for("meta_date_idx_d", "id_business_dates"),
    series_id_for("natl_Monetary_bi_m", "id_foreign_reserves"),
})

# Snapshot `yfinance` -> series_id
YFINANCE_SERIES = {
    "USDIDR": series_id_for("glob_Monetary_yahoo_d", "usd_idr"),
    "EURIDR": series_id_for("glob_Monetary_yahoo_d", "eur_idr"),
    "CNYIDR": series_id_for("glob_Monetary_yahoo_d", "cny_idr"),
    "JPYIDR": series_id_for("glob_Monetary_yahoo_d", "jpy_idr"),
    "DXY": series_id_for("glob_Monetary_yahoo_d", "dollar_index"),
    "IHSG": series_id_for("natl_FinancialMarket_yahoo_d", "idx_composite"),
    "DJI": series_id_for("glob_FinancialMarket_yahoo_d", "dji_index"),
    "SPX": series_id_for("glob_FinancialMarket_yahoo_d", "spx_index"),
    "US5Y": series_id_for("glob_FinancialMarket_yahoo_d", "us_gov_5yr"),
    "US10Y": series_id_for("glob_FinancialMarket_yahoo_d", "us_gov_10yr"),
    "US30Y": series_id_for("glob_FinancialMarket_yahoo_d", "us_gov_30yr"),
    "GOLD": series_id_for("glob_Commodity_yahoo_d", "gold_comex_futures"),
    "WTI": series_id_for("glob_Commodity_yahoo_d", "crude_oil_wti"),
    "BRENT": series_id_for("glob_Commodity_yahoo_d", "crude_oil_brent_price"),
    "NEWCASTLE_COAL": series_id_for("glob_Commodity_te_d", "coal_newcastle"),
    "CPO": series_id_for("glob_Commodity_te_d", "my_cpo"),
    "IDXENERGY": series_id_for("natl_FinancialMarket_yahoo_d", "idx_energy"),
    "IDXBASIC": series_id_for("natl_FinancialMarket_yahoo_d", "idx_basic"),
    "IDXINDUST": series_id_for("natl_FinancialMarket_yahoo_d", "idx_industrials"),
    "IDXCYCLIC": series_id_for("natl_FinancialMarket_yahoo_d", "idx_cyclical"),
    "IDXNONCYC": series_id_for("natl_FinancialMarket_yahoo_d", "idx_noncyclical"),
    "IDXHEALTH": series_id_for("natl_FinancialMarket_yahoo_d", "idx_healthcare"),
    "IDXFINANCE": series_id_for("natl_FinancialMarket_yahoo_d", "idx_finance"),
    "IDXPROPERT": series_id_for("natl_FinancialMarket_yahoo_d", "idx_property"),
    "IDXTECHNO": series_id_for("natl_FinancialMarket_yahoo_d", "idx_techno"),
    "IDXINFRA": series_id_for("natl_FinancialMarket_yahoo_d", "idx_infra"),
    "IDXTRANS": series_id_for("natl_FinancialMarket_yahoo_d", "idx_transport"),
}

EQUITY_INDEX_SERIES = {
    "NASDAQ": series_id_for("glob_FinancialMarket_yahoo_d", "nasdaq_composite"),
    "NIKKEI": series_id_for("glob_FinancialMarket_yahoo_d", "nky_index"),
    "HSI": series_id_for("glob_FinancialMarket_yahoo_d", "hsi_index"),
    "KLCI": series_id_for("glob_FinancialMarket_yahoo_d", "fbmklci_index"),
    "STI": series_id_for("glob_FinancialMarket_yahoo_d", "sti_index"),
}

INTL_FLOW_SERIES = {
    "China": series_id_for("glob_EquityFlow_safe_m", "cn_inbound_equity_flow"),
    "Japan": series_id_for("glob_EquityFlow_moj_m", "jp_inbound_equity_flow"),
    "Malaysia": series_id_for("glob_EquityFlow_bm_m", "my_inbound_equity_flow"),
    "United States": series_id_for("glob_EquityFlow_fred_m", "us_inbound_equity_flow"),
}

MACRO_SERIES = {
    "FED Fund Rate (%)": series_id_for("glob_Rates_te_d", "us_fed_funds_rate"),
    "Inflasi Indonesia YoY (%)": series_id_for("natl_Macro_te_m", "id_inflation_yoy"),
    "M2 (% YoY)": series_id_for("natl_Macro_te_m", "id_m2_yoy"),
    "Kredit/Pembiayaan (% YoY) - BI": series_id_for("natl_Macro_bi_m", "id_credit_yoy"),
    "DPK (% YoY) - BI": series_id_for("natl_Macro_bi_m", "id_dpk_yoy"),
}

BI_SERIES = (
    ("bi_rate", "bi_rate_date", series_id_for("natl_Rates_bi_d", "id_bi_rate")),
    ("indonia", "indonia_date", series_id_for("natl_Rates_bi_d", "id_indonia")),
    ("jisdor", "jisdor_date", series_id_for("natl_Rates_bi_d", "id_jisdor")),
)

CAPITAL_FLOW_SERIES = {
    "Saham": series_id_for("natl_StockFlow_idx_d", "id_idx_netforeignflow_daily_idr"),
    "Obligasi": series_id_for("natl_BondFlow_djppr_d", "id_bond_netforeignflow_daily_idr"),
}

GOLD_SPOT_SERIES = series_id_for("glob_Commodity_te_d", "gold_spot")
ANTAM_SERIES = series_id_for("natl_Commodity_antam_d", "id_gold_antam_sell_1g")
SBN_SERIES = (
    ("5.0", series_id_for("natl_SbnYield_phei_d", "id_sbn_5y")),
    ("10.0", series_id_for("natl_SbnYield_phei_d", "id_sbn_10y")),
)
MONETARY_SERIES = series_id_for("natl_Monetary_bi_m", "id_monetary_operations")
ERAPI_SERIES = series_id_for("glob_Monetary_erapi_d", "usd_idr_backup")


def _points_from_history(history) -> list[tuple[str, float]]:
    points = []
    for point in history if isinstance(history, list) else []:
        if not isinstance(point, dict):
            continue
        date = str(point.get("date") or point.get("dates") or "").strip()[:10]
        value = (
            point.get("close")
            if point.get("close") is not None
            else point.get("value")
            if point.get("value") is not None
            else point.get("balance_idr_trillion")
        )
        if date and isinstance(value, (int, float)) and not isinstance(value, bool):
            points.append((date, float(value)))
    return points


def _single_point(date, value) -> list[tuple[str, float]]:
    day = str(date or "").strip()[:10]
    if day and isinstance(value, (int, float)) and not isinstance(value, bool):
        return [(day, float(value))]
    return []


def _month_start(month) -> str | None:
    text = str(month or "").strip()
    if len(text) >= 7 and text[4] == "-" and text[:4].isdigit() and text[5:7].isdigit():
        return f"{text[:4]}-{text[5:7]}-01"
    return None


def observations_from_snapshot(snapshot: dict) -> list[dict]:
    """Ubah snapshot pipeline menjadi observasi `(series_id, dates, value)`.

    Hanya series yang terdaftar di katalog yang dikembalikan, sehingga isi
    tabel observasi tetap konsisten dengan `meta_timeseries`.
    """
    if not isinstance(snapshot, dict):
        return []
    observations: list[dict] = []

    def add(series_id, points):
        if series_id not in SERIES_BY_ID or series_id in OBSERVATION_SKIP:
            return
        for date, value in points:
            if not date or value is None:
                continue
            observations.append({"series_id": series_id, "dates": date, "value": float(value)})

    market = snapshot.get("yfinance") or {}
    for key, series_id in YFINANCE_SERIES.items():
        reading = market.get(key) if isinstance(market, dict) else None
        if not isinstance(reading, dict):
            continue
        points = _points_from_history(reading.get("history"))
        if not points:
            points = _single_point(reading.get("date"), reading.get("last"))
        add(series_id, points)

    gold_spot = market.get("GOLD_SPOT") if isinstance(market, dict) else None
    gold_points = _points_from_history(snapshot.get("_gold_spot_history"))
    if not gold_points and isinstance(gold_spot, dict):
        gold_points = _single_point(gold_spot.get("date"), gold_spot.get("last"))
    add(GOLD_SPOT_SERIES, gold_points)

    # Riwayat kumulatif antarversi laporan (IHSG sektor, SBN, Antam).
    try:
        from market_report.domain.index_sectors import IDX_IC_SECTOR_INDEXES

        labels = {label: key for key, _, label, _ in IDX_IC_SECTOR_INDEXES}
    except Exception:  # pragma: no cover - tabel sektor selalu tersedia
        labels = {}
    sector_history = snapshot.get("_index_sector_history") or {}
    if isinstance(sector_history, dict):
        for label, points in sector_history.items():
            key = labels.get(label)
            if key and key in YFINANCE_SERIES:
                add(YFINANCE_SERIES[key], _points_from_history(points))

    add(SBN_SERIES[1][1], _points_from_history(snapshot.get("_sbn_history")))
    add(ANTAM_SERIES, _points_from_history(snapshot.get("_antam_gold_history")))

    phei = snapshot.get("phei") or {}
    curve = phei.get("yield_curve") if isinstance(phei, dict) else None
    if isinstance(curve, dict):
        as_of = phei.get("as_of_date")
        for tenor, series_id in SBN_SERIES:
            entry = curve.get(tenor) or {}
            if isinstance(entry, dict):
                add(series_id, _single_point(as_of, entry.get("today")))

    bi = snapshot.get("bi") or {}
    if isinstance(bi, dict):
        from market_report.services.history_service import source_date_iso

        for value_key, date_key, series_id in BI_SERIES:
            add(series_id, _single_point(source_date_iso(bi.get(date_key)), bi.get(value_key)))

    antam = snapshot.get("antam_gold") or {}
    if isinstance(antam, dict):
        add(ANTAM_SERIES, _single_point(antam.get("date"), antam.get("price")))

    capital_flow = snapshot.get("capital_flow") or {}
    if isinstance(capital_flow, dict):
        for bucket, series_id in CAPITAL_FLOW_SERIES.items():
            reading = capital_flow.get(bucket) or {}
            if isinstance(reading, dict):
                add(series_id, _points_from_history(reading.get("history")))

    monetary = snapshot.get("monetary_operations") or {}
    if isinstance(monetary, dict):
        add(MONETARY_SERIES, _points_from_history(monetary.get("history")))

    macro = snapshot.get("macro_indicators") or {}
    if isinstance(macro, dict):
        for label, series_id in MACRO_SERIES.items():
            reading = macro.get(label) or {}
            if not isinstance(reading, dict):
                continue
            points = []
            for month, value in (reading.get("observations") or {}).items():
                day = _month_start(month)
                if day and isinstance(value, (int, float)) and not isinstance(value, bool):
                    points.append((day, float(value)))
            add(series_id, points)

    flows = snapshot.get("international_equity_flows") or {}
    if isinstance(flows, dict):
        for country, series_id in INTL_FLOW_SERIES.items():
            reading = flows.get(country) or {}
            if not isinstance(reading, dict):
                continue
            points = []
            for point in reading.get("observations") or []:
                if isinstance(point, dict) and isinstance(point.get("usd_mn"), (int, float)):
                    day = str(point.get("date") or "").strip()[:10]
                    if day:
                        points.append((day, float(point["usd_mn"])))
            add(series_id, points)

    equity = snapshot.get("equity") or {}
    indices = equity.get("indices") if isinstance(equity, dict) else None
    if isinstance(indices, dict):
        for key, series_id in EQUITY_INDEX_SERIES.items():
            reading = indices.get(key) or {}
            if isinstance(reading, dict):
                add(series_id, _single_point(reading.get("date"), reading.get("last")))

    fx_backup = snapshot.get("fx_backup") or {}
    if isinstance(fx_backup, dict) and fx_backup.get("USDIDR"):
        stamp = str(fx_backup.get("time_last_update_utc") or "").strip()
        try:
            day = parsedate_to_datetime(stamp).date().isoformat()
        except (TypeError, ValueError):
            day = datetime.now(timezone.utc).date().isoformat()
        add(ERAPI_SERIES, _single_point(day, fx_backup.get("USDIDR")))

    logger.info("Katalog pipeline: %d observasi dari %d series", len(observations),
                len({item["series_id"] for item in observations}))
    return observations


def sync_observations(snapshot: dict, repository=None, limit: int = 420) -> int:
    """Tulis observasi snapshot ke backend aktif; kembalikan jumlah titik."""
    observations = observations_from_snapshot(snapshot)
    if not observations:
        return 0
    if repository is None:
        from market_report.config import market_data_directory
        from market_report.infrastructure.repositories.timeseries_repository import (
            configured_timeseries_repository,
        )

        repository = configured_timeseries_repository(market_data_directory())
    grouped: dict[str, list[dict]] = {}
    for point in observations:
        grouped.setdefault(point["series_id"], []).append(
            {"dates": point["dates"], "value": point["value"]}
        )
    for series_id, points in grouped.items():
        repository.bulk_upsert_observations(series_id, points, limit=limit)
    return len(observations)
