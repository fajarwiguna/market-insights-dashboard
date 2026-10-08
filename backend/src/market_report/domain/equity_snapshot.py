"""Deterministic equity snapshot, ranking and factual narrative suggestions."""
from __future__ import annotations

import math
from collections import defaultdict

PERFORMANCE_INDICES = (
    ("DJI", "^DJI", "Dow Jones (US)"),
    ("SPX", "^GSPC", "S&P 500 (US)"),
    ("NASDAQ", "^IXIC", "Nasdaq (US)"),
    ("NIKKEI", "^N225", "Nikkei 225 (Japan)"),
    ("HSI", "^HSI", "HSI (Hong Kong)"),
    ("KLCI", "^KLSE", "KLCI (Malaysia)"),
    ("STI", "^STI", "STI (Singapore)"),
    ("IHSG", "^JKSE", "JCI (Indonesia)"),
    *((key, symbol, label) for key, symbol, label in (
        ("IDXFINANCE", "IDXFINANCE.JK", "IDXFIN"),
        ("IDXHEALTH", "IDXHEALTH.JK", "IDXHEALTH"),
        ("IDXBASIC", "IDXBASIC.JK", "IDXBASIC"),
        ("IDXENERGY", "IDXENERGY.JK", "IDXENERGY"),
        ("IDXINDUST", "IDXINDUST.JK", "IDXINDUS"),
        ("IDXNONCYC", "IDXNONCYC.JK", "IDXNON-CYC"),
        ("IDXCYCLIC", "IDXCYCLIC.JK", "IDXCYCLIC"),
        ("IDXPROPERT", "IDXPROPERT.JK", "IDXPROPERT"),
        ("IDXTECHNO", "IDXTECHNO.JK", "IDXTECH"),
        ("IDXINFRA", "IDXINFRA.JK", "IDXINFRA"),
        ("IDXTRANS", "IDXTRANS.JK", "IDXTRANS"),
    )),
)

SECTOR_NAMES = {
    "Energy": "Energi", "Basic Materials": "Bahan Baku",
    "Industrials": "Industri", "Consumer Cyclical": "Konsumen Siklikal",
    "Consumer Defensive": "Konsumen Non-Siklikal", "Healthcare": "Kesehatan",
    "Financial Services": "Keuangan", "Real Estate": "Properti",
    "Technology": "Teknologi", "Utilities": "Utilitas",
    "Communication Services": "Komunikasi",
}


def finite(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)


def fmt(value, decimals=2, signed=False) -> str:
    if not finite(value):
        return "—"
    result = f"{abs(value):,.{decimals}f}".translate(str.maketrans({",": ".", ".": ","}))
    return ("−" if value < 0 else "+" if signed and value > 0 else "") + result


def rank_stocks(stocks: list[dict]) -> tuple[list[dict], list[dict]]:
    valid = [row for row in stocks if finite(row.get("contribution_points"))]
    leaders = sorted((row for row in valid if row["contribution_points"] > 0),
                     key=lambda row: (-row["contribution_points"], row["ticker"]))[:10]
    laggards = sorted((row for row in valid if row["contribution_points"] < 0),
                      key=lambda row: (row["contribution_points"], row["ticker"]))[:10]
    return leaders, laggards


def build_equity_snapshot(source: dict, report: dict | None = None) -> dict:
    report = report or {}
    quotes = source.get("indices") or {}
    day, previous_day = source.get("trading_date"), source.get("previous_trading_date")
    ihsg = quotes.get("IHSG") or {}
    stocks, excluded = [], []
    seen = set()
    for row in source.get("stocks") or []:
        ticker = row.get("ticker")
        if not ticker or ticker in seen:
            continue
        seen.add(ticker)
        if (row.get("date") != day or row.get("prev_date") != previous_day
                or row.get("split_detected") or not all(finite(row.get(k)) and row[k] > 0
                for k in ("close", "previous_close", "shares_outstanding"))):
            excluded.append(ticker)
            continue
        stocks.append({**row, "change_pct": (row["close"] / row["previous_close"] - 1) * 100,
                       "previous_market_cap": row["previous_close"] * row["shares_outstanding"]})

    denominator = sum(row["previous_market_cap"] for row in stocks)
    usable_index = finite(ihsg.get("prev")) and ihsg["prev"] > 0 and day and previous_day
    for row in stocks:
        row["weight"] = row["previous_market_cap"] / denominator if denominator else None
        row["contribution_points"] = (ihsg["prev"] * row["weight"] * row["change_pct"] / 100
                                      if denominator and usable_index else None)
        row["sector"] = SECTOR_NAMES.get(row.get("sector"), row.get("sector") or "Belum terklasifikasi")

    leaders, laggards = rank_stocks(stocks)
    sectors = defaultdict(float)
    for row in stocks:
        if finite(row.get("contribution_points")):
            sectors[row["sector"]] += row["contribution_points"]
    sector_rows = sorted(({"sector": key, "contribution_points": value} for key, value in sectors.items()),
                         key=lambda row: (-abs(row["contribution_points"]), row["sector"]))
    suggestions, suggested = [], set()
    candidates = [(row, "Kontributor positif terbesar") for row in leaders[:3]]
    candidates += [(row, "Kontributor negatif terbesar") for row in laggards[:3]]
    for sector in sector_rows[:2]:
        members = [row for row in stocks if row["sector"] == sector["sector"]
                   and finite(row.get("contribution_points"))
                   and row["contribution_points"] * sector["contribution_points"] > 0]
        if members:
            candidates.append((max(members, key=lambda row: abs(row["contribution_points"])),
                               f"Penggerak sektor {sector['sector']}"))
    for row, reason in candidates:
        if row["ticker"] not in suggested:
            suggested.add(row["ticker"])
            suggestions.append({"ticker": row["ticker"], "company": row["company"],
                                "sector": row["sector"], "reason": reason,
                                "contribution_points": row["contribution_points"]})

    performance = []
    for key, _, label in PERFORMANCE_INDICES:
        reading = quotes.get(key) or {}
        performance.append({"id": key, "label": label, "level": reading.get("last"),
                            "change_pct": reading.get("change_pct"), "date": reading.get("date"),
                            "prev_date": reading.get("prev_date"),
                            "availability": "available" if finite(reading.get("last")) else "unavailable"})

    # Yahoo does not expose foreign flows or Indonesian macro observations.
    # Keep these slots editable, without borrowing unrelated/stale sources.
    flow_date, flow_usd, flow_idr = None, None, None
    coal, inflation = {}, {}

    direction = "menguat" if (ihsg.get("change_pct") or 0) > 0 else "melemah" if (ihsg.get("change_pct") or 0) < 0 else "bergerak mendatar"
    headline = f"IHSG {direction}"
    if sector_rows:
        headline += f", sektor {sector_rows[0]['sector'].lower()} menjadi penggerak"
    opening = (f"IHSG {direction} {fmt(ihsg.get('change_pct'))}% ke level {fmt(ihsg.get('last'), 0)}. "
               f"Perubahan dihitung terhadap sesi {previous_day}. Kontribusi saham merupakan estimasi berbasis kapitalisasi pasar Yahoo Finance.")
    macro_text = (f"Inflasi tercatat {fmt(inflation.get('today'))}% pada periode {inflation.get('date') or 'terakhir yang tersedia'}. "
                  if finite(inflation.get("today")) else "Data inflasi untuk laporan ini belum tersedia. ")
    macro_text += "Analis dapat menambahkan agenda ekonomi dan evaluasi indeks yang relevan."
    foreign_text = (f"Net transaksi asing saham sebesar USD {fmt(flow_usd)} juta, berdasarkan data {flow_date}."
                    if finite(flow_usd) else "Data transaksi asing saham tidak tersedia dari yfinance. Analis dapat mengisi bagian ini berdasarkan sumber yang telah diverifikasi.")
    discussed = leaders[:2] + laggards[:2]
    stock_text = "; ".join(f"{row['ticker']} ({fmt(row['change_pct'], signed=True)}%; estimasi {fmt(row['contribution_points'], signed=True)} poin)" for row in discussed)
    sector_text = "; ".join(f"{row['sector']} ({fmt(row['contribution_points'], signed=True)} poin)" for row in sector_rows[:2])
    sector_narrative = (f"Kontribusi sektoral terbesar berdasarkan klasifikasi Yahoo Finance: {sector_text}. " if sector_text else "")
    sector_narrative += f"Saham yang dibahas: {stock_text}." if stock_text else "Data kontribusi saham belum cukup untuk mengusulkan pembahasan."
    count = source.get("universe_count") or len(seen)
    coverage = len(stocks) / count if count else 0
    estimated_sum = sum(row["contribution_points"] for row in stocks if finite(row.get("contribution_points")))
    actual_delta = ihsg["last"] - ihsg["prev"] if all(finite(ihsg.get(k)) for k in ("last", "prev")) else None
    return {
        "schema_version": 1, "report_id": source.get("snapshot_id"),
        "report_date": day, "fetched_at": source.get("fetched_at"), "source": "Yahoo Finance via yfinance",
        "status": "partial" if stocks and usable_index else "unavailable",
        "methodology": "Estimated previous-close market-cap weights over valid Yahoo JKT equities; not official IHSG weights.",
        "sector_methodology": "Yahoo Finance classification, not IDX-IC membership.",
        "coverage": {"universe_count": count, "valid_count": len(stocks), "ratio": coverage,
                     "excluded_tickers": excluded, "discovery_complete": source.get("discovery_complete", False),
                     "membership_verified": False, "estimated_points": estimated_sum,
                     "actual_ihsg_points": actual_delta,
                     "residual_points": actual_delta - estimated_sum if actual_delta is not None else None},
        "market_performance": performance, "stocks": stocks,
        "market_leaders": leaders, "market_laggards": laggards,
        "sector_contributions": sector_rows, "narrative_suggestions": suggestions,
        "headline": headline, "ihsg": ihsg,
        "foreign_flow": {"net_idr": flow_idr, "net_usd_mn": flow_usd, "date": flow_date},
        "coal": {"mtd_pct": coal.get("mtd_pct"), "date": coal.get("date")},
        "foreign_flow_rows": [{"country": "Indonesia", "date": flow_date,
                               "daily": flow_usd, **{key.lower(): None for key in ("WTD", "MTD", "QTD", "YTD", "12M")}}],
        "narratives": [
            {"id": "market", "title": "Pergerakan IHSG dan sikap investor", "text": opening},
            {"id": "macro", "title": "Inflasi dan penyesuaian indeks", "text": macro_text},
            {"id": "foreign", "title": "Arus dana asing", "text": foreign_text},
            {"id": "sector", "title": "Pergerakan sektoral", "text": sector_narrative},
        ],
    }
