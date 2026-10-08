"""Fetch closed daily bars with yfinance, discover JKT equities and cache snapshots."""
from __future__ import annotations

import hashlib
import json
import logging
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone

from market_report.config import market_data_directory
from market_report.domain.equity_snapshot import PERFORMANCE_INDICES, SECTOR_NAMES, build_equity_snapshot, finite

logger = logging.getLogger(__name__)
JAKARTA = timezone(timedelta(hours=7))


def _read(path) -> dict:
    try:
        result = json.loads(path.read_text(encoding="utf-8"))
        return result if isinstance(result, dict) else {}
    except (OSError, ValueError):
        return {}


def _save(value: dict, path) -> None:
    from market_report.calculate import persist_json_data
    persist_json_data(value, path)


def discover_equities(yf, now: datetime) -> dict:
    path = market_data_directory() / "equity_universe.json"
    cached = _read(path)
    if cached.get("date") == now.date().isoformat() and cached.get("complete"):
        return cached
    stocks, expected = {}, None
    for offset in range(0, 10000, 250):
        result = yf.screen(yf.EquityQuery("eq", ["exchange", "JKT"]), offset=offset,
                           size=250, sortField="ticker", sortAsc=True)
        expected = int(result.get("total", 0))
        quotes = result.get("quotes") or []
        for quote in quotes:
            symbol = quote.get("symbol", "")
            if re.fullmatch(r"[A-Z]{4}\.JK", symbol) and quote.get("quoteType") == "EQUITY":
                stocks[symbol] = {"symbol": symbol, "ticker": symbol[:-3],
                                  "company": quote.get("longName") or quote.get("shortName") or symbol[:-3],
                                  "shares_outstanding": quote.get("sharesOutstanding"),
                                  "market_cap": quote.get("marketCap"), "sector": quote.get("sector"),
                                  "quote_price": quote.get("regularMarketPrice")}
        if offset + len(quotes) >= expected:
            break
        if not quotes:
            raise RuntimeError("Yahoo screener returned an incomplete universe")
    if not stocks:
        raise RuntimeError("Yahoo screener returned no JKT equities")

    # Yahoo screen returns sectors through filtered discovery, avoiding hundreds
    # of per-ticker info calls. This classification is explicitly not IDX-IC.
    def sector_members(sector):
        members = []
        for offset in range(0, 10000, 250):
            query = yf.EquityQuery("and", [yf.EquityQuery("eq", ["exchange", "JKT"]),
                                         yf.EquityQuery("eq", ["sector", sector])])
            result = yf.screen(query, size=250, offset=offset, sortField="ticker", sortAsc=True)
            rows = result.get("quotes") or []
            members.extend(row.get("symbol") for row in rows)
            if offset + len(rows) >= int(result.get("total", 0)) or not rows:
                break
        return sector, members
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(sector_members, sector) for sector in SECTOR_NAMES]
        for future in futures:
            try:
                sector, members = future.result()
                for symbol in members:
                    if symbol in stocks:
                        stocks[symbol]["sector"] = sector
            except Exception:
                logger.warning("Yahoo sector discovery unavailable", exc_info=True)
    # Metadata overrides can mark non-IHSG tickers ineligible and supply an
    # analyst-maintained sector. Market prices still come exclusively from Yahoo.
    registry = _read(market_data_directory() / "equity_registry.json")
    for symbol, row in list(stocks.items()):
        override = registry.get(row["ticker"]) or {}
        if override.get("eligible") is False:
            del stocks[symbol]
        elif override.get("sector"):
            row["sector"] = override["sector"]
    result = {"date": now.date().isoformat(), "complete": offset + len(quotes) >= expected,
              "yahoo_total": expected, "stocks": list(stocks.values())}
    _save(result, path)
    return result


def _bars(frame, cutoff: str) -> list[dict]:
    rows = []
    for stamp, row in frame.iterrows():
        day = stamp.strftime("%Y-%m-%d")
        close = row.get("Close")
        if day <= cutoff and finite(close) and close > 0:
            volume, split = row.get("Volume"), row.get("Stock Splits", 0)
            rows.append({"date": day, "close": float(close),
                         "volume": float(volume) if finite(volume) else None,
                         "split": float(split) if finite(split) else 0})
    return sorted(rows, key=lambda row: row["date"])


def _download(yf, symbols: list[str]):
    return yf.download(symbols, period="1mo", interval="1d", auto_adjust=False,
                       actions=True, group_by="ticker", threads=4, progress=False,
                       timeout=15, multi_level_index=True)


def _quote_index(info: dict, day: str, previous_day: str) -> dict | None:
    """Sector chart history is absent; accept a dated completed Yahoo quote."""
    stamp = info.get("regularMarketTime")
    last, previous = info.get("regularMarketPrice"), info.get("regularMarketPreviousClose")
    if not finite(stamp) or not all(finite(value) and value > 0 for value in (last, previous)):
        return None
    quote_date = datetime.fromtimestamp(stamp, JAKARTA).date().isoformat()
    # Reject live/future-session quotes instead of mixing them into yesterday.
    if quote_date != day:
        return None
    return {"last": last, "prev": previous, "change_pct": (last / previous - 1) * 100,
            "date": quote_date, "prev_date": previous_day, "price_basis": "Yahoo dated quote"}


def fetch_equity_source() -> dict:
    import yfinance as yf
    now = datetime.now(JAKARTA)
    # Exclude today's unfinished daily candle, including during closing auctions.
    cutoff = (now.date() if (now.hour, now.minute) >= (17, 0) else now.date() - timedelta(days=1)).isoformat()
    index_symbols = [symbol for _, symbol, _ in PERFORMANCE_INDICES]
    index_frame = _download(yf, index_symbols)
    ihsg_bars = _bars(index_frame["^JKSE"], cutoff)
    if len(ihsg_bars) < 2:
        raise RuntimeError("Two completed IHSG sessions are required")
    previous_day, day = ihsg_bars[-2]["date"], ihsg_bars[-1]["date"]
    indices = {}
    for key, symbol, _ in PERFORMANCE_INDICES:
        try:
            bars = _bars(index_frame[symbol], day)
            if len(bars) >= 2:
                latest, previous = bars[-1], bars[-2]
                indices[key] = {"last": latest["close"], "prev": previous["close"],
                                "change_pct": (latest["close"] / previous["close"] - 1) * 100,
                                "date": latest["date"], "prev_date": previous["date"]}
        except (KeyError, ValueError):
            logger.warning("Index %s unavailable", symbol)
    def sector_quote(item):
        key, symbol, _ = item
        return key, _quote_index(yf.Ticker(symbol).get_info(), day, previous_day)
    missing_sectors = [item for item in PERFORMANCE_INDICES if item[0].startswith("IDX") and item[0] not in indices]
    with ThreadPoolExecutor(max_workers=3) as pool:
        futures = [pool.submit(sector_quote, item) for item in missing_sectors]
        for future in futures:
            try:
                key, quote = future.result()
                if quote:
                    indices[key] = quote
            except Exception:
                logger.warning("Yahoo sector quote unavailable", exc_info=True)
    universe = discover_equities(yf, now)
    stocks = []
    metadata = universe["stocks"]
    for start in range(0, len(metadata), 64):
        batch = metadata[start:start + 64]
        try:
            frame = _download(yf, [row["symbol"] for row in batch])
        except Exception:
            logger.warning("Yahoo stock batch unavailable", exc_info=True)
            frame = None
        for item in batch:
            result = {**item, "date": None, "prev_date": None, "close": None,
                      "previous_close": None, "volume_shares": None,
                      "shares_as_of": universe["date"], "shares_basis": "Yahoo current shares outstanding proxy"}
            try:
                bars = _bars(frame[item["symbol"]], day) if frame is not None else []
                lookup = {row["date"]: row for row in bars}
                latest, previous = lookup.get(day), lookup.get(previous_day)
                if latest and previous:
                    result.update(date=day, prev_date=previous_day, close=latest["close"],
                                  previous_close=previous["close"], volume_shares=latest["volume"],
                                  split_detected=bool(latest["split"]))
            except (KeyError, ValueError):
                pass
            stocks.append(result)
        logger.info("Equity bars %d/%d", min(start + 64, len(metadata)), len(metadata))
    stamp = now.isoformat(timespec="seconds")
    return {"snapshot_id": f"equity-{day}-{hashlib.sha256(stamp.encode()).hexdigest()[:12]}",
            "trading_date": day, "previous_trading_date": previous_day,
            "fetched_at": stamp, "indices": indices, "stocks": stocks,
            "universe_count": len(metadata), "discovery_complete": universe["complete"]}


def persist_equity_snapshot(snapshot: dict) -> None:
    if snapshot.get("status") == "unavailable":
        raise RuntimeError("Equity snapshot has no usable stock contributions")
    root = market_data_directory()
    _save(snapshot, root / "equity_versions" / f"{snapshot['report_id']}.json")
    _save(snapshot, root / "equity_snapshot.json")


def load_equity_snapshot() -> dict:
    return _read(market_data_directory() / "equity_snapshot.json")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    source = fetch_equity_source()
    snapshot = build_equity_snapshot(source)
    persist_equity_snapshot(snapshot)
    print(json.dumps({"report_id": snapshot["report_id"], "date": snapshot["report_date"],
                      "status": snapshot["status"], "valid": snapshot["coverage"]["valid_count"],
                      "universe": snapshot["coverage"]["universe_count"]}))
