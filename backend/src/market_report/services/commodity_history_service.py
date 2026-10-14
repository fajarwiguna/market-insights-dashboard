"""Dated commodity futures history; never mix providers within a return."""

import base64
from datetime import date, datetime, timezone
import json
import math
import zlib

import requests
from bs4 import BeautifulSoup

from market_report.config import market_data_directory
from market_report.domain.market_periods import period_changes, rolling_month_change

HISTORY_SLUGS = {"NEWCASTLE_COAL": "newcastle-coal-futures", "CPO": "palm-oil"}
TE_SERIES = {"NEWCASTLE_COAL": ("coal", "XAL1:COM"), "CPO": ("palm-oil", "PLO:COM")}
TE_CHART_URL = "https://d3ii0wo49og5mi.cloudfront.net/markets/"
# Public chart encoding used by Trading Economics' mk.min.js dataMagic function.
TE_CHART_ENCODING_KEY = b"tradingeconomics-charts-core-api-key"


def _valid_close(value) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool) \
        and math.isfinite(value) and value > 0


def _trading_economics_history(symbol: str) -> list[dict]:
    """Read/cache the public daily chart, preserving year-end baselines."""
    cache = market_data_directory() / "commodity_history" / f"te-{symbol.split(':')[0].lower()}.json"
    observations = {}

    def merge(payload):
        if not isinstance(payload, dict) or payload.get("symbol") != symbol:
            return
        history = payload.get("history")
        for point in history if isinstance(history, list) else []:
            if not isinstance(point, dict) or not _valid_close(point.get("close")):
                continue
            try:
                day = date.fromisoformat(point["date"])
            except (KeyError, TypeError, ValueError):
                continue
            if day <= date.today():
                observations[day.isoformat()] = point["close"]

    try:
        merge(json.loads(cache.read_text(encoding="utf-8")))
    except (OSError, ValueError):
        pass
    try:
        response = requests.get(
            TE_CHART_URL + symbol.lower(), params={"span": "1y", "interval": "1d"},
            headers={"User-Agent": "Mozilla/5.0", "Accept": "application/json"}, timeout=15,
        )
        response.raise_for_status()
        payload = response.json()
        if isinstance(payload, str):
            encoded = base64.b64decode(payload, validate=True)
            decoded = bytes(value ^ TE_CHART_ENCODING_KEY[index % len(TE_CHART_ENCODING_KEY)]
                            for index, value in enumerate(encoded))
            payload = json.loads(zlib.decompress(decoded, wbits=47))
        if not isinstance(payload, dict):
            raise ValueError("Invalid Trading Economics chart payload")
        series_list = payload.get("series")
        for series in series_list if isinstance(series_list, list) else []:
            if not isinstance(series, dict) or str(series.get("symbol", "")).upper() != symbol:
                continue
            points = []
            rows = series.get("data")
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, list) or len(row) < 2 or not _valid_close(row[1]):
                    continue
                try:
                    day = datetime.fromtimestamp(row[0], timezone.utc).date().isoformat()
                except (TypeError, ValueError, OverflowError, OSError):
                    continue
                points.append({"date": day, "close": row[1]})
            merge({"symbol": symbol, "history": points})
        if observations:
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps({"symbol": symbol, "history": [
                {"date": day, "close": value} for day, value in sorted(observations.items())][-420:]
            }), encoding="utf-8")
    except (requests.RequestException, OSError, ValueError, TypeError, zlib.error):
        # Cached closes remain usable as baselines; they never replace the live quote.
        pass
    return [{"date": day, "close": value} for day, value in sorted(observations.items())][-420:]


def enrich_commodity_history(snapshot: dict, versions: list[dict]) -> None:
    market = snapshot.get("yfinance") or {}
    for key, slug in HISTORY_SLUGS.items():
        current = market.get(key)
        if not isinstance(current, dict):
            continue
        # Retain actual observations from the same provider across publications.
        observations = {}
        te_slug, te_symbol = TE_SERIES[key]
        is_te = current.get("source") == f"https://tradingeconomics.com/commodity/{te_slug}"
        if is_te:
            existing = period_changes(current.get("history"), current.get("date"), current.get("last"))
            if any(existing.get(f"{period}_pct") is None for period in ("wtd", "mtd", "ytd")):
                observations.update({point["date"]: point["close"]
                                     for point in _trading_economics_history(te_symbol)
                                     if point["date"] <= (current.get("date") or "")})
        for report in reversed(versions):
            reading = (report.get("_source_snapshot") or {}).get("yfinance", {}).get(key, {})
            if reading.get("source") != current.get("source"):
                continue
            for point in reading.get("history") or []:
                if isinstance(point, dict):
                    observations[point.get("date")] = point.get("close")
            observations[reading.get("date")] = reading.get("last")
        for point in current.get("history") or []:
            if isinstance(point, dict):
                observations[point.get("date")] = point.get("close")
        observations[current.get("date")] = current.get("last")
        current["history"] = [{"date": day, "close": value} for day, value in sorted(
            ((day, value) for day, value in observations.items() if isinstance(day, str)
             and isinstance(value, (int, float)) and not isinstance(value, bool)
             and math.isfinite(value) and value > 0))][-420:]
        periods = period_changes(current["history"], current.get("date"), current.get("last"))
        if is_te:
            missing = [label for period, label in (("wtd", "WtD"), ("mtd", "MtD"), ("ytd", "YtD"))
                       if periods.get(f"{period}_pct") is None]
            current["availability"] = "partial" if missing else "available"
            current["availability_note"] = (
                "Harga referensi Trading Economics berbasis OTC/CFD. "
                "WtD, MtD, dan YtD dihitung dari histori harian sumber yang sama "
                "dengan acuan penutupan terakhir sebelum awal periode kalender. "
                "Perubahan 1 bulan adalah periode bergulir. "
                + (f"Histori pembanding belum tersedia untuk {', '.join(missing)}." if missing else "")
            )
        if all(periods.get(f"{period}_pct") is not None for period in ("wtd", "mtd", "ytd")):
            continue
        alternative = _investing_history(slug)
        if alternative is None:
            continue
        merged = {}
        for report in reversed(versions):
            saved = (report.get("_source_snapshot") or {}).get("yfinance", {}).get(key, {})
            if saved.get("source") == alternative["source"]:
                for point in saved.get("history") or []:
                    if isinstance(point, dict) and isinstance(point.get("date"), str):
                        value = point.get("close")
                        if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0:
                            merged[point["date"]] = value
        merged.update({point["date"]: point["close"] for point in alternative["history"]})
        history = [{"date": day, "close": value} for day, value in sorted(merged.items())
                   if day <= alternative["history"][-1]["date"]][-420:]
        latest, previous = history[-1], history[-2]
        # An older alternative must not overwrite the latest source observation.
        if current.get("date") and latest["date"] < current["date"]:
            continue
        current.update({
            "last": latest["close"], "prev": previous["close"], "date": latest["date"],
            "history": history, "source": alternative["source"], "source_name": "Investing.com",
            "dtd_pct": round((latest["close"] / previous["close"] - 1) * 100, 4),
            "rolling_1m_pct": rolling_month_change(history, latest["date"], latest["close"]),
        })
        periods = period_changes(history, latest["date"], latest["close"])
        missing = [label for period, label in (("wtd", "WtD"), ("mtd", "MtD"), ("ytd", "YtD"))
                   if periods.get(f"{period}_pct") is None]
        if current["rolling_1m_pct"] is None:
            missing.append("1M bergulir")
        current["availability"] = "partial" if missing else "available"
        current["availability_note"] = (
            "Harga penutupan futures Investing.com. Semua perubahan dihitung dari seri yang sama. "
            + (f"Histori pembanding belum tersedia untuk {', '.join(missing)}." if missing else "")
        )


def _investing_history(slug: str) -> dict | None:
    url = f"https://www.investing.com/commodities/{slug}-historical-data"
    cache = market_data_directory() / "commodity_history" / f"{slug}.json"
    payload = None
    try:
        response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=15)
        response.raise_for_status()
        soup = BeautifulSoup(response.text, "lxml")
        points = {}
        for row in soup.select("tr"):
            cells = [cell.get_text(" ", strip=True) for cell in row.select("td")]
            if len(cells) < 7:
                continue
            try:
                day = datetime.strptime(cells[0], "%b %d, %Y").date().isoformat()
                value = float(cells[1].replace(",", ""))
            except ValueError:
                continue
            if math.isfinite(value) and value > 0:
                points[day] = value
        if len(points) >= 2:
            payload = {"source": url, "history": [{"date": day, "close": value}
                       for day, value in sorted(points.items())]}
            cache.parent.mkdir(parents=True, exist_ok=True)
            cache.write_text(json.dumps(payload), encoding="utf-8")
    except (requests.RequestException, OSError, ValueError):
        pass
    if payload is None:
        try:
            payload = json.loads(cache.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
    if payload.get("source") != url or not isinstance(payload.get("history"), list):
        return None
    history = payload["history"]
    try:
        age = (date.today() - date.fromisoformat(history[-1]["date"])).days
        valid = len(history) >= 2 and 0 <= age <= 7 and all(
            date.fromisoformat(point["date"]) <= date.today()
            and isinstance(point["close"], (int, float)) and not isinstance(point["close"], bool)
            and math.isfinite(point["close"]) and point["close"] > 0 for point in history)
        ordered = sorted({point["date"]: point["close"] for point in history}.items())
    except (KeyError, TypeError, ValueError, IndexError):
        return None
    return {"source": url, "history": [{"date": day, "close": value} for day, value in ordered]} if valid and len(ordered) >= 2 else None
