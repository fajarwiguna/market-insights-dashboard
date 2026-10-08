"""Deterministic equity snapshot, ranking and factual narrative suggestions."""
from __future__ import annotations

import math
from datetime import date
from copy import deepcopy
from collections import defaultdict
from market_report.domain.index_sectors import IDX_IC_SECTOR_INDEXES

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


MONTHS = ("Januari", "Februari", "Maret", "April", "Mei", "Juni", "Juli", "Agustus", "September", "Oktober", "November", "Desember")


def _listing(items: list[str]) -> str:
    return ", ".join(items[:-1]) + " dan " + items[-1] if len(items) > 1 else "".join(items)


def compose_equity_narratives(snapshot: dict, report: dict) -> list[dict]:
    """Write factual analyst prose; provenance belongs in metadata/footer."""
    day = snapshot.get("report_date") or ""
    ihsg = snapshot.get("ihsg") or {}
    change = ihsg.get("change_pct")
    direction = "naik" if finite(change) and change > 0 else "turun" if finite(change) and change < 0 else "bergerak mendatar"
    market = f"IHSG {direction} {fmt(abs(change))}% ke level {fmt(ihsg.get('last'), 0)}." if finite(change) else "Pergerakan IHSG menunggu data perdagangan terbaru."
    raw_market = (report.get("_source_snapshot") or {}).get("yfinance") or {}
    bars = sorted((point for point in (raw_market.get("IHSG") or {}).get("history") or []
                   if isinstance(point.get("date"), str) and point["date"] < day
                   and finite(point.get("close")) and point["close"] > 0), key=lambda point: point["date"])
    if len(bars) >= 2 and bars[-1]["date"] == ihsg.get("prev_date"):
        previous_change = (bars[-1]["close"] / bars[-2]["close"] - 1) * 100
        movement = "penguatan" if previous_change > 0 else "pelemahan" if previous_change < 0 else "pergerakan mendatar"
        market += f" Pada perdagangan sebelumnya, indeks mencatat {movement} {fmt(abs(previous_change))}%."

    observations = ((report.get("macro_indicators") or {}).get("Inflasi Indonesia YoY (%)") or {}).get("observations") or {}
    months = sorted(month for month, value in observations.items()
                    if len(month) == 7 and month < day[:7] and finite(value))
    macro = "Perkembangan inflasi dan agenda penyesuaian indeks menjadi faktor yang perlu dicermati dalam menilai prospek pasar."
    if months:
        latest = months[-1]
        year, month = map(int, latest.split("-"))
        macro = f"Inflasi {MONTHS[month - 1]} {year} tercatat {fmt(observations[latest])}% YoY."
        if len(months) >= 2:
            previous = months[-2]
            previous_year, previous_month = map(int, previous.split("-"))
            comparison = "naik menjadi" if observations[latest] > observations[previous] else "turun menjadi" if observations[latest] < observations[previous] else "stabil di"
            macro = (f"Inflasi {MONTHS[month - 1]} {year} {comparison} {fmt(observations[latest])}% YoY, "
                     f"dibandingkan {fmt(observations[previous])}% pada {MONTHS[previous_month - 1]} {previous_year}.")
        macro += " Perkembangan harga pangan dan arah kebijakan moneter menjadi faktor yang perlu dicermati."

    flow = snapshot.get("foreign_flow") or {}
    usd, idr, flow_day = flow.get("net_usd_mn"), flow.get("net_idr"), flow.get("date")
    foreign = "Perkembangan transaksi investor asing menjadi salah satu indikator yang perlu dicermati untuk menilai arus dana di pasar saham."
    def amount(net_usd, net_idr=None):
        if finite(net_idr):
            scale, unit = (1e12, "Tn") if abs(net_idr) >= 1e12 else (1e9, "Bn")
            return f"IDR {fmt(abs(net_idr) / scale)} {unit}"
        return f"USD {fmt(abs(net_usd))} Mn"
    if finite(usd):
        sign = "outflow" if usd < 0 else "inflow" if usd > 0 else "flow"
        foreign = f"Pasar saham mencatat net foreign {sign} {amount(usd, idr)}"
        if flow_day and flow_day != day:
            dated = date.fromisoformat(flow_day)
            foreign += f" pada {dated.day} {MONTHS[dated.month - 1]} {dated.year}"
        history = ((report.get("capital_flow") or {}).get("Saham") or {}).get("history") or []
        prior = sorted((point for point in history if isinstance(point.get("date"), str)
                        and flow_day and point["date"] < flow_day and finite(point.get("close"))), key=lambda point: point["date"])
        if prior and (date.fromisoformat(flow_day) - date.fromisoformat(prior[-1]["date"])).days <= 4:
            previous = prior[-1]
            previous_usd = previous["close"]
            fx = next((point for point in (raw_market.get("USDIDR") or {}).get("history") or []
                       if point.get("date") == previous["date"] and finite(point.get("close")) and point["close"] > 0), None)
            previous_idr = previous_usd * 1e6 * fx["close"] if fx else None
            if not finite(idr) or previous_idr is not None:
                previous_sign = "outflow" if previous_usd < 0 else "inflow" if previous_usd > 0 else "flow"
                connective = "berbalik dari" if usd * previous_usd < 0 else "dibandingkan"
                foreign += f", {connective} net foreign {previous_sign} {amount(previous_usd, previous_idr if finite(idr) else None)} pada perdagangan sebelumnya"
        foreign += "."

    sectors = snapshot.get("sector_contributions") or []
    positives = [row["sector"].lower() for row in sectors if row.get("contribution_points", 0) > 0 and row["sector"] != "Belum terklasifikasi"][:3]
    negatives = [row["sector"].lower() for row in sectors if row.get("contribution_points", 0) < 0 and row["sector"] != "Belum terklasifikasi"][:3]
    sector = []
    sector_names = {key: label.lower() for key, _, label, _ in IDX_IC_SECTOR_INDEXES}
    readings = [row for row in snapshot.get("market_performance") or []
                if row.get("id") in sector_names and row.get("date") == day and finite(row.get("change_pct"))]
    rising = [sector_names[row["id"]] for row in readings if row["change_pct"] > 0]
    falling = [sector_names[row["id"]] for row in readings if row["change_pct"] < 0]
    if len(readings) == len(IDX_IC_SECTOR_INDEXES):
        if len(falling) == len(readings):
            sector.append("Seluruh indeks sektor melemah.")
        elif len(rising) == len(readings):
            sector.append("Seluruh indeks sektor menguat.")
        elif len(falling) >= len(readings) - 3 and rising and len(rising) + len(falling) == len(readings):
            sector.append(f"Hampir seluruh sektor melemah, kecuali {_listing(rising)}.")
        elif len(rising) >= len(readings) - 3 and falling and len(rising) + len(falling) == len(readings):
            sector.append(f"Hampir seluruh sektor menguat, kecuali {_listing(falling)}.")
        else:
            sector.append(f"Sebanyak {len(rising)} sektor menguat dan {len(falling)} sektor melemah.")
    elif negatives:
        sector.append(f"Saham sektor {_listing(negatives)} memberi tekanan pada IHSG.")
    if len(readings) != len(IDX_IC_SECTOR_INDEXES) and positives:
        sector.append(f"Saham sektor {_listing(positives)} menjadi penopang indeks.")
    coal = snapshot.get("coal") or {}
    if finite(coal.get("mtd_pct")):
        movement = "naik" if coal["mtd_pct"] > 0 else "turun" if coal["mtd_pct"] < 0 else "bergerak mendatar"
        sector.append(f"Harga batubara {movement} {fmt(abs(coal['mtd_pct']))}% MTD.")
    for key, label in (("market_leaders", "movers"), ("market_laggards", "laggards")):
        names = [f"{row['ticker']} ({fmt(row['change_pct'], signed=True)}%)" for row in (snapshot.get(key) or [])[:3]]
        if names:
            sector.append(f"{_listing(names)} menjadi {label} IHSG.")
    return [
        {"id": "market", "title": "Pergerakan IHSG dan sikap Investor", "text": market},
        {"id": "macro", "title": "Inflasi dan penyesuaian indeks", "text": macro},
        {"id": "foreign", "title": "Arus dana asing", "text": foreign},
        {"id": "sector", "title": "Pergerakan sektoral", "text": " ".join(sector) or "Pergerakan sektor dan saham penggerak menjadi perhatian dalam menilai arah IHSG."},
    ]


def enrich_equity_indicators(snapshot: dict, report: dict) -> dict:
    """Attach dated supplemental observations without changing equity prices."""
    result = deepcopy(snapshot)
    day = result.get("report_date")
    if not day:
        return result
    sector_names = {key: label for key, _, label, _ in IDX_IC_SECTOR_INDEXES}
    report_sectors = report.get("index_sectors") or {}
    saved_sector_history = ((report.get("_source_snapshot") or {}).get("_index_sector_history") or {})
    previous_session = (result.get("ihsg") or {}).get("prev_date")
    for row in result.get("market_performance") or []:
        if row.get("id") not in sector_names:
            continue
        if finite(row.get("level")) and finite(row.get("change_pct")) and row.get("date") == day:
            continue
        reading = report_sectors.get(sector_names[row["id"]]) or {}
        if reading.get("date") != day:
            # The active report may contain today's live quote while the equity
            # document uses yesterday's close. Read both exact sessions from
            # its saved history instead of discarding all sector observations.
            history = {point.get("date"): point.get("close")
                       for point in saved_sector_history.get(sector_names[row["id"]]) or []}
            current_close, previous_close = history.get(day), history.get(previous_session)
            if (reading.get("source") and finite(current_close) and current_close > 0
                    and finite(previous_close) and previous_close > 0):
                reading = {"date": day, "today": current_close, "prev_date": previous_session,
                           "source": reading["source"],
                           "dtd_pct": (current_close / previous_close - 1) * 100}
        change = reading.get("dtd_pct")
        if not finite(change):
            change = reading.get("change_pct")
        if (reading.get("date") == day and reading.get("source")
                and finite(reading.get("today")) and reading["today"] > 0 and finite(change)):
            row.update(level=reading["today"], change_pct=change, date=day,
                       prev_date=reading.get("prev_date"), availability="available", source=reading["source"])
    flow = (report.get("capital_flow") or {}).get("Saham") or {}
    flow_date = flow.get("date")
    periods = flow.get("periods") or {}
    if (isinstance(flow_date, str) and flow_date <= day and flow.get("source")
            and flow.get("unit") == "USD juta" and finite(periods.get("1D"))):
        usd = periods["1D"]
        raw_market = (report.get("_source_snapshot") or {}).get("yfinance") or {}
        fx = raw_market.get("USDIDR") or {}
        # Use the transaction date's FX observation, never today's FX rate.
        fx_point = next((point for point in fx.get("history") or []
                         if point.get("date") == flow_date and finite(point.get("close"))
                         and point["close"] > 0), None)
        net_idr = usd * 1e6 * fx_point["close"] if fx_point else None
        result["foreign_flow"] = {"net_idr": net_idr, "net_usd_mn": usd, "date": flow_date,
                                  "source": flow["source"], "source_url": flow.get("source_url"),
                                  "fx_date": fx_point["date"] if fx_point else None, "stale": flow_date != day}
        # 1W means five rolling sessions; it must not be relabeled WTD.
        result["foreign_flow_rows"] = [{"country": "Indonesia", "date": flow_date, "daily": usd,
            "wtd": None, "mtd": periods.get("MtD"), "qtd": periods.get("QtD"),
            "ytd": periods.get("YtD"), "12m": None}]
    from market_report.domain.international_equity_flows import foreign_flow_rows
    international = (report.get("_source_snapshot") or {}).get("international_equity_flows") or {}
    # build_report_data attaches the raw snapshot after this domain function runs.
    international = report.get("international_equity_flows") or international
    if international:
        indonesia = [row for row in result.get("foreign_flow_rows") or [] if row.get("country") == "Indonesia"]
        for row in indonesia:
            row.update(frequency="daily", latest=row.get("daily"), source="BEI")
        result["foreign_flow_rows"] = indonesia + foreign_flow_rows(international, day)
    coal = (report.get("commodities") or {}).get("Coal (Newcastle)") or {}
    coal_date = coal.get("date")
    if isinstance(coal_date, str) and coal_date <= day and coal.get("source") and finite(coal.get("mtd_pct")):
        result["coal"] = {"mtd_pct": coal["mtd_pct"], "date": coal_date,
                          "price": coal.get("today"), "source": coal["source"],
                          "source_name": coal.get("source_name") or "Newcastle", "stale": coal_date != day}
    if result.get("foreign_flow", {}).get("source") or result.get("coal", {}).get("source"):
        result["supplemental_report_id"] = report.get("report_id")
    result["narratives"] = compose_equity_narratives(result, report)
    return result


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

    # The dated supplemental adapter below fills foreign flow and Newcastle
    # from the published report; missing observations remain editable blanks.
    flow_date, flow_usd, flow_idr = None, None, None
    coal = {}

    direction = "menguat" if (ihsg.get("change_pct") or 0) > 0 else "melemah" if (ihsg.get("change_pct") or 0) < 0 else "bergerak mendatar"
    headline = f"IHSG {direction}"
    if sector_rows:
        headline += f", sektor {sector_rows[0]['sector'].lower()} menjadi penggerak"
    count = source.get("universe_count") or len(seen)
    coverage = len(stocks) / count if count else 0
    estimated_sum = sum(row["contribution_points"] for row in stocks if finite(row.get("contribution_points")))
    actual_delta = ihsg["last"] - ihsg["prev"] if all(finite(ihsg.get(k)) for k in ("last", "prev")) else None
    result = {
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
        "narratives": [],
    }
    return enrich_equity_indicators(result, report)
