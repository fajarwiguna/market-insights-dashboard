"""Capital-flow adapters backed by IDX trading data and DJPPR SBN holdings."""

from __future__ import annotations

import base64
import json
import math
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urljoin
from zoneinfo import ZoneInfo

import requests

from market_report.config import market_data_directory


IDX_PAGE_URL = (
    "https://www.idx.id/en/market-data/statistical-reports/digital-statistic/"
    "monthly/equity-trading-by-investor/table-daily-trading-by-type-of-investor"
)
IDX_API_URL = "https://www.idx.id/primary/DigitalStatistic/GetApiData"
DJPPR_PAGE_URL = "https://djppr.kemenkeu.go.id/kepemilikansbndomestikyangdapatdiperdagangkan"
DJPPR_PAGE_API = "https://api-djppr.kemenkeu.go.id/web/api/v1/page"
DJPPR_API_ROOT = "https://api-djppr.kemenkeu.go.id/web/api/v1/"
MONTHS_ID = {
    "januari": 1, "februari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8,
    "september": 9, "oktober": 10, "november": 11, "desember": 12,
}
MONTHS_EN = {
    "jan": 1, "feb": 2, "mar": 3, "apr": 4, "may": 5, "jun": 6,
    "jul": 7, "aug": 8, "sep": 9, "oct": 10, "nov": 11, "dec": 12,
}
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "application/json,text/html,application/pdf,*/*",
}
PERIOD_KEYS = ("1D", "1W", "MtD", "QtD", "YtD")
CACHE_DIR = market_data_directory() / "capital_flow"
CACHE_DIR.mkdir(parents=True, exist_ok=True)


def _today() -> date:
    return datetime.now(ZoneInfo("Asia/Jakarta")).date()


def _read_json(path: Path) -> Any:
    try:
        with path.open(encoding="utf-8") as source:
            return json.load(source)
    except (OSError, ValueError):
        return None


def _write_json(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    with temporary.open("w", encoding="utf-8") as output:
        json.dump(value, output, ensure_ascii=False, indent=2, default=str)
    temporary.replace(path)


def _parse_date(value: Any) -> date | None:
    if value is None:
        return None
    raw = str(value).strip()
    if not raw:
        return None
    timestamp = re.fullmatch(r"/Date\((-?\d+)(?:[+-]\d+)?\)/", raw)
    if timestamp:
        try:
            return datetime.fromtimestamp(int(timestamp.group(1)) / 1000, tz=ZoneInfo("UTC")).date()
        except (OverflowError, OSError, ValueError):
            return None
    try:
        return date.fromisoformat(raw[:10])
    except ValueError:
        pass
    for pattern in ("%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y%m%d", "%d %b %Y"):
        try:
            return datetime.strptime(raw, pattern).date()
        except ValueError:
            continue
    match = re.search(r"(\d{1,2})[- ]([A-Za-z]{3})[- ](\d{2,4})", raw)
    if match:
        month = MONTHS_EN.get(match.group(2).lower())
        year = int(match.group(3))
        year += 2000 if year < 100 else 0
        if month:
            try:
                return date(year, month, int(match.group(1)))
            except ValueError:
                pass
    return None


def _number(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return float(value) if math.isfinite(value) else None
    raw = str(value).strip()
    if not raw or raw in {"-", "—", "–"}:
        return None
    negative = (raw.startswith("(") and raw.endswith(")")) or raw.startswith("-")
    raw = re.sub(r"[^0-9.,]", "", raw)
    if not raw:
        return None
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        whole, decimal = raw.rsplit(",", 1)
        raw = f"{whole.replace(',', '')}.{decimal}" if len(decimal) <= 2 else raw.replace(",", "")
    elif "." in raw:
        whole, decimal = raw.rsplit(".", 1)
        if len(decimal) == 3:
            raw = raw.replace(".", "")
    try:
        number = float(raw)
    except ValueError:
        return None
    number = -number if negative else number
    return number if math.isfinite(number) else None


def _field(record: dict[str, Any], *names: str) -> Any:
    normalized = {str(key).lower(): value for key, value in record.items()}
    for name in names:
        if name.lower() in normalized:
            return normalized[name.lower()]
    return None


def _flatten_records(value: Any) -> list[dict[str, Any]]:
    result: list[dict[str, Any]] = []
    if isinstance(value, list):
        for item in value:
            result.extend(_flatten_records(item))
    elif isinstance(value, dict):
        result.append(value)
        nested = value.get("months")
        if isinstance(nested, list):
            result.extend(_flatten_records(nested))
    return result


def _month_cache_file(year: int, month: int) -> Path:
    return CACHE_DIR / "idx" / f"{year:04d}-{month:02d}.json"


def _fetch_idx_month(year: int, month: int) -> dict[str, Any]:
    query = base64.b64encode(json.dumps({
        "year": str(year), "month": str(month), "quarter": 0, "type": "monthly",
    }, separators=(",", ":")).encode("utf-8")).decode("ascii")
    headers = {
        **HEADERS,
        "Referer": IDX_PAGE_URL,
        "Origin": "https://www.idx.id",
        "X-Requested-With": "XMLHttpRequest",
    }
    with requests.Session() as session:
        session.headers.update(headers)
        # The IDX statistic endpoint may require its public site session cookie.
        try:
            session.get(IDX_PAGE_URL, timeout=12)
        except requests.RequestException:
            pass
        source_rows: dict[str, list[dict[str, Any]]] = {}
        for investor, source_id in (
            ("domestic", "LINK_TABLE_DAILY_TRADING_INVESTOR_DOMESTIC"),
            ("foreign", "LINK_TABLE_DAILY_TRADING_INVESTOR_FOREIGN"),
        ):
            response = session.get(IDX_API_URL, params={
                "urlName": source_id,
                "query": query,
                "isPrint": "False",
                "cumulative": "false",
            }, timeout=15)
            response.raise_for_status()
            payload = response.json()
            rows = payload.get("data") if isinstance(payload, dict) else None
            if not isinstance(rows, list):
                raise ValueError(f"Respons IDX {investor} bulan {year}-{month:02d} tidak memiliki daftar data.")
            source_rows[investor] = _flatten_records(rows)
    return {"source_rows": source_rows, "fetched_at": datetime.now().astimezone().isoformat()}


def _cached_idx_month(year: int, month: int, today: date) -> tuple[dict[str, Any] | None, str | None]:
    path = _month_cache_file(year, month)
    cached = _read_json(path)
    current_month = (year, month) == (today.year, today.month)
    recently_closed = (year, month) == ((today.replace(day=1) - timedelta(days=1)).year,
                                       (today.replace(day=1) - timedelta(days=1)).month)
    max_age = 30 * 60 if current_month else 24 * 60 * 60 if recently_closed else None
    cache_fresh = isinstance(cached, dict) and max_age is not None and cached.get("fetched_at")
    if cache_fresh:
        try:
            fetched = datetime.fromisoformat(cached["fetched_at"])
            cache_fresh = (datetime.now().astimezone() - fetched.astimezone()).total_seconds() < max_age
        except (TypeError, ValueError):
            cache_fresh = False
    if isinstance(cached, dict) and isinstance(cached.get("source_rows"), dict) and (max_age is None or cache_fresh):
        return cached, None
    if isinstance(cached, dict) and cached.get("error") and cached.get("fetched_at"):
        try:
            failed_at = datetime.fromisoformat(cached["fetched_at"])
            if (datetime.now().astimezone() - failed_at.astimezone()).total_seconds() < 60 * 60:
                return None, f"IDX {year}-{month:02d}: {cached['error']}"
        except (TypeError, ValueError):
            pass
    try:
        fresh = _fetch_idx_month(year, month)
        _write_json(path, fresh)
        return fresh, None
    except Exception as error:
        if isinstance(cached, dict) and isinstance(cached.get("source_rows"), dict):
            return cached, f"IDX {year}-{month:02d} gagal diperbarui; memakai cache sebelumnya: {error}"
        _write_json(path, {"error": str(error), "fetched_at": datetime.now().astimezone().isoformat()})
        return None, f"IDX {year}-{month:02d}: {error}"


def _usd_idr_by_date(market_snapshot: dict[str, Any]) -> dict[date, float]:
    raw = market_snapshot.get("USDIDR") if isinstance(market_snapshot, dict) else None
    history = raw.get("history", []) if isinstance(raw, dict) else []
    result = {}
    for point in history if isinstance(history, list) else []:
        if not isinstance(point, dict):
            continue
        day = _parse_date(point.get("date"))
        rate = _number(point.get("close"))
        if day and rate and rate > 0:
            result[day] = rate
    return result


def _fx_rate(day: date, rates: dict[date, float]) -> float | None:
    exact = rates.get(day)
    if exact is not None:
        return exact
    # Yahoo FX history can omit a calendar day or label the close on the
    # adjacent date. Use only the most recent rate at or before the IDX
    # transaction date, and reject gaps longer than a trading-weekend window.
    prior_days = [rate_day for rate_day in rates if rate_day < day]
    if not prior_days:
        return None
    prior_day = max(prior_days)
    return rates[prior_day] if (day - prior_day).days <= 4 else None


def _records_to_stock_history(month_data: dict[tuple[int, int], dict[str, Any]],
                              fx_rates: dict[date, float]) -> tuple[list[dict[str, Any]], list[str]]:
    domestic: dict[date, float] = {}
    foreign: dict[date, float] = {}
    for key, destination in (("domestic", domestic), ("foreign", foreign)):
        for month in month_data.values():
            rows = (month.get("source_rows") or {}).get(key, [])
            for record in rows if isinstance(rows, list) else []:
                if not isinstance(record, dict):
                    continue
                day = _parse_date(_field(record, "date", "Date"))
                if day is None:
                    continue
                value_key = "domesticForeignValue" if key == "domestic" else "foreignDomesticValue"
                value = _number(_field(record, value_key))
                if value is not None:
                    destination[day] = value
    source_days = sorted(set(domestic) & set(foreign))
    history = []
    for day in source_days:
        rate = _fx_rate(day, fx_rates)
        if rate is None:
            continue
        # Foreign net purchase = domestic investors selling to foreign investors
        # minus foreign investors selling to domestic investors. Same-origin trades cancel.
        flow_idr = domestic[day] - foreign[day]
        history.append({"date": day.isoformat(), "close": flow_idr / rate / 1_000_000})
    return history, [day.isoformat() for day in source_days]


def _month_starts(start: date, end: date) -> list[date]:
    months = []
    cursor = start.replace(day=1)
    while cursor <= end:
        months.append(cursor)
        cursor = (cursor.replace(day=28) + timedelta(days=4)).replace(day=1)
    return months


def _period_sum(series: list[dict[str, Any]], start: date, end: date) -> float | None:
    values = [
        float(point["close"])
        for point in series
        if start <= date.fromisoformat(point["date"]) <= end
    ]
    return round(sum(values), 3) if values else None


def _stock_reading(history: list[dict[str, Any]], source_dates: list[str], coverage: set[str],
                   errors: list[str], today: date) -> dict[str, Any]:
    periods: dict[str, float | None] = {key: None for key in PERIOD_KEYS}
    history_by_date = {point["date"]: float(point["close"]) for point in history}
    source_days = [date.fromisoformat(raw) for raw in source_dates]
    latest = source_days[-1] if source_days else None
    if latest is not None:
        if latest.isoformat() in history_by_date:
            periods["1D"] = round(history_by_date[latest.isoformat()], 3)
        recent_days = source_days[-5:]
        if len(recent_days) == 5 and (latest - recent_days[0]).days <= 10 \
                and all(day.isoformat() in history_by_date for day in recent_days):
            periods["1W"] = round(sum(history_by_date[day.isoformat()] for day in recent_days), 3)
        month_start = latest.replace(day=1)
        quarter_month = ((latest.month - 1) // 3) * 3 + 1
        quarter_start = latest.replace(month=quarter_month, day=1)
        year_start = latest.replace(month=1, day=1)
        for key, start in (("MtD", month_start), ("QtD", quarter_start), ("YtD", year_start)):
            required_months = {item.strftime("%Y-%m") for item in _month_starts(start, latest)}
            period_days = [day for day in source_days if start <= day <= latest]
            if required_months.issubset(coverage) and period_days \
                    and all(day.isoformat() in history_by_date for day in period_days):
                periods[key] = _period_sum(history, start, latest)
    missing = [key for key, value in periods.items() if value is None]
    note = "Net beli investor asing di pasar saham BEI; USD juta, dikonversi memakai kurs USD/IDR pada tanggal transaksi atau kurs terakhir sebelumnya bila tanggal itu tidak tersedia. 1W menjumlahkan lima sesi perdagangan terakhir."
    if latest:
        note += f" Data terakhir per {latest.isoformat()}."
    stale = bool(latest and (today - latest).days > 4)
    if stale and latest:
        note += f" Data BEI terakhir tersedia pada {latest.isoformat()}; angka ditandai sebagai observasi terakhir, bukan data hari ini."
    if errors:
        note += " Sebagian data sumber belum dapat diperbarui."
    if missing:
        note += f" Periode belum lengkap: {', '.join(missing)}."
    return {
        "unit": "USD juta", "periods": periods,
        "availability": "stale" if stale and history else "available" if not missing and not errors else "partial" if history else "unavailable",
        "availability_note": note if history else ("Sumber transaksi harian BEI belum dapat diakses." + (f" {errors[0]}" if errors else "")),
        "date": latest.isoformat() if latest else None,
        "history": history[-420:],
        "source": "IDX — Table Daily Trading by Type of Investor",
        "source_url": IDX_PAGE_URL,
        "errors": errors[:5],
    }


def _idx_stock_flow(fx_rates: dict[date, float], today: date) -> dict[str, Any]:
    months = [(today.year, month) for month in range(1, today.month + 1)]
    results: dict[tuple[int, int], dict[str, Any]] = {}
    errors: list[str] = []
    with ThreadPoolExecutor(max_workers=4) as pool:
        futures = {
            pool.submit(_cached_idx_month, year, month, today): (year, month)
            for year, month in months
        }
        for future in as_completed(futures):
            key = futures[future]
            try:
                cached, error = future.result()
                if cached:
                    results[key] = cached
                if error:
                    errors.append(error)
            except Exception as error:  # one failed month must not hide the others
                errors.append(f"IDX {key[0]}-{key[1]:02d}: {error}")
    history, source_dates = _records_to_stock_history(results, fx_rates)
    coverage = {f"{year:04d}-{month:02d}" for year, month in results}
    return _stock_reading(history, source_dates, coverage, errors, today)


def _walk_djppr_attachments(value: Any) -> list[dict[str, Any]]:
    results: list[dict[str, Any]] = []
    if isinstance(value, dict):
        description = value.get("@deskripsi") or value.get("@description")
        link = value.get("@link") or value.get("link")
        if description and link:
            parsed = _parse_description_date(str(description))
            if parsed:
                results.append({"description": str(description), "date": parsed.isoformat(), "url": urljoin(DJPPR_API_ROOT, str(link))})
        for child in value.values():
            results.extend(_walk_djppr_attachments(child))
    elif isinstance(value, list):
        for child in value:
            results.extend(_walk_djppr_attachments(child))
    return results


def _parse_description_date(value: str) -> date | None:
    match = re.search(r"(\d{1,2})\s+([A-Za-z]+)\s+(20\d{2})", value)
    if not match:
        return None
    month = MONTHS_ID.get(match.group(2).lower()) or MONTHS_EN.get(match.group(2)[:3].lower())
    if not month:
        return None
    try:
        return date(int(match.group(3)), month, int(match.group(1)))
    except ValueError:
        return None


def _djppr_attachments() -> list[dict[str, Any]]:
    session = requests.Session()
    session.headers.update(HEADERS)
    response = session.get(DJPPR_PAGE_API, params={"url": "kepemilikansbndomestikyangdapatdiperdagangkan"}, timeout=20)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("Data", payload.get("data", {})) if isinstance(payload, dict) else {}
    content = data.get("PageContentLive") if isinstance(data, dict) else None
    if isinstance(content, str):
        content = json.loads(content)
    attachments = _walk_djppr_attachments(content)
    unique = {item["url"]: item for item in attachments}
    if not unique:
        raise ValueError("Halaman DJPPR tidak menampilkan lampiran data harian kepemilikan SBN.")
    return sorted(unique.values(), key=lambda item: item["date"])


def _select_djppr_documents(attachments: list[dict[str, Any]], today: date) -> list[dict[str, Any]]:
    latest = [item for item in attachments if date.fromisoformat(item["date"]) <= today]
    if not latest:
        return []
    latest_item = max(latest, key=lambda item: item["date"])
    latest_item_date = date.fromisoformat(latest_item["date"])
    month_start = latest_item_date.replace(day=1)
    quarter_start = latest_item_date.replace(month=((latest_item_date.month - 1) // 3) * 3 + 1, day=1)
    year_start = latest_item_date.replace(month=1, day=1)
    cutoffs = [
        latest_item_date,
        month_start - timedelta(days=1),
        quarter_start - timedelta(days=1),
        year_start - timedelta(days=1),
    ]
    selected = {latest_item["url"]: latest_item}
    for cutoff in cutoffs[1:]:
        candidates = [item for item in latest if date.fromisoformat(item["date"]) <= cutoff]
        if candidates:
            item = max(candidates, key=lambda value: value["date"])
            selected[item["url"]] = item
    # Include the previous month-end file for a five-session window across months.
    previous_month_end = month_start - timedelta(days=1)
    candidates = [item for item in latest if date.fromisoformat(item["date"]) <= previous_month_end]
    if candidates:
        item = max(candidates, key=lambda value: value["date"])
        selected[item["url"]] = item
    return sorted(selected.values(), key=lambda item: item["date"])


def _media_cache_path(url: str) -> Path:
    media_id = url.rstrip("/").rsplit("/", 1)[-1]
    return CACHE_DIR / "djppr" / f"{media_id}.pdf"


def _fetch_djppr_pdf(item: dict[str, Any], refresh: bool) -> bytes:
    path = _media_cache_path(item["url"])
    if path.is_file():
        if not refresh or datetime.now().timestamp() - path.stat().st_mtime < 30 * 60:
            return path.read_bytes()
    response = requests.get(item["url"], headers=HEADERS, timeout=30)
    response.raise_for_status()
    content = response.content
    if not content.startswith(b"%PDF"):
        raise ValueError(f"Lampiran DJPPR {item['description']} tidak berupa PDF.")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(content)
    return content


def _parse_pdf_day(value: str) -> date | None:
    match = re.search(r"(\d{1,2})[- ]([A-Za-z]{3})[- ](\d{2,4})", value)
    if not match:
        return None
    month = MONTHS_EN.get(match.group(2).lower())
    year = int(match.group(3))
    year += 2000 if year < 100 else 0
    if month:
        try:
            return date(year, month, int(match.group(1)))
        except ValueError:
            return None
    return None


def _pdf_nonresident_observations(content: bytes) -> list[dict[str, Any]]:
    try:
        import pymupdf
    except ImportError as error:
        raise RuntimeError("Parser PDF membutuhkan PyMuPDF yang tercantum di backend/requirements.txt.") from error
    document = pymupdf.open(stream=content, filetype="pdf")
    observations: dict[date, float] = {}
    page_data = []
    document_label_y = None
    for page in document:
        words = page.get_text("words")
        headers = []
        for word in words:
            text = str(word[4]).strip()
            day = _parse_pdf_day(text)
            if day and float(word[1]) < 100:
                headers.append(((float(word[0]) + float(word[2])) / 2, day))
        label_lines: dict[int, list[tuple[float, str]]] = {}
        for word in words:
            x0, y0, text = float(word[0]), float(word[1]), str(word[4]).lower()
            if x0 < 150 and y0 < page.rect.height / 2:
                label_lines.setdefault(round(y0 / 3), []).append((y0, text))
        label_rows = []
        for line in label_lines.values():
            words_on_line = [text for _, text in line]
            normalized = re.sub(r"[^a-z]+", " ", " ".join(words_on_line)).split()
            if "non" in normalized and "residen" in normalized and "bank" not in normalized:
                label_rows.append(sum(y for y, _ in line) / len(line))
        page_label_y = min(label_rows) if label_rows else None
        if document_label_y is None and page_label_y is not None:
            document_label_y = page_label_y
        page_data.append((page, words, headers, page_label_y))

    for page, words, headers, page_label_y in page_data:
        if not headers:
            continue
        # DJPPR splits long months across landscape pages. Continuation pages
        # omit row labels but preserve their vertical position.
        target_y = page_label_y if page_label_y is not None else document_label_y
        if target_y is None:
            continue
        numeric_by_date: dict[date, list[tuple[float, float]]] = {day: [] for _, day in headers}
        left_edge = min(center for center, _ in headers) - 35
        right_edge = max(center for center, _ in headers) + 35
        for word in words:
            x0, y0, x1, _y1, text = word[:5]
            if abs(float(y0) - target_y) > 2.5 or not left_edge <= float(x0) <= right_edge:
                continue
            value = _number(text)
            if value is None:
                continue
            center = (float(x0) + float(x1)) / 2
            header_x, day = min(headers, key=lambda item: abs(item[0] - center))
            numeric_by_date[day].append((center, value))
        for day, values in numeric_by_date.items():
            # The third amount per date is the TOTAL SBN holding, after SUN and SBSN.
            if len(values) >= 3:
                ordered = sorted(values, key=lambda item: item[0])
                observations[day] = ordered[-1][1]
    document.close()
    if not observations:
        raise ValueError("Baris Non Residen dan tanggal pada PDF kepemilikan SBN DJPPR tidak berhasil dibaca.")
    return [{"date": day.isoformat(), "balance_idr_trillion": value} for day, value in sorted(observations.items())]


def _djppr_holdings_history(today: date) -> tuple[list[dict[str, Any]], list[str], str | None]:
    cache_path = CACHE_DIR / "djppr_history.json"
    cached = _read_json(cache_path)
    history = {
        str(item.get("date")): _number(item.get("balance_idr_trillion"))
        for item in (cached.get("history", []) if isinstance(cached, dict) else [])
        if isinstance(item, dict) and _parse_date(item.get("date")) is not None
    }
    errors: list[str] = []
    source_date = None
    try:
        attachments = _djppr_attachments()
        selected = _select_djppr_documents(attachments, today)
        for item in selected:
            source_date = max(source_date or item["date"], item["date"])
            # The latest file can be revised as new sessions are added; archive PDFs are immutable.
            is_latest = item["date"] == max(selected_item["date"] for selected_item in selected)
            points = _pdf_nonresident_observations(_fetch_djppr_pdf(item, refresh=is_latest))
            for point in points:
                history[point["date"]] = float(point["balance_idr_trillion"])
        _write_json(cache_path, {
            "history": [
                {"date": day, "balance_idr_trillion": value}
                for day, value in sorted(history.items())[-520:] if value is not None
            ],
            "updated_at": datetime.now().astimezone().isoformat(),
        })
    except Exception as error:
        errors.append(f"DJPPR: {error}")
    points = [
        {"date": day, "balance_idr_trillion": value}
        for day, value in sorted(history.items()) if value is not None
    ]
    if points:
        source_date = points[-1]["date"]
    return points, errors, source_date


def _balance_at_or_before(history: list[dict[str, Any]], cutoff: date) -> dict[str, Any] | None:
    matches = [point for point in history if date.fromisoformat(point["date"]) <= cutoff]
    return matches[-1] if matches else None


def _bond_reading(history: list[dict[str, Any]], fx_rates: dict[date, float], errors: list[str]) -> dict[str, Any]:
    periods: dict[str, float | None] = {key: None for key in PERIOD_KEYS}
    latest = history[-1] if history else None
    latest_day = date.fromisoformat(latest["date"]) if latest else None
    if latest and latest_day:
        latest_balance = float(latest["balance_idr_trillion"])
        rate = _fx_rate(latest_day, fx_rates)

        def usd_million(delta_idr_trillion: float | None) -> float | None:
            if delta_idr_trillion is None or rate is None:
                return None
            return round(delta_idr_trillion * 1_000_000 / rate, 3)

        if len(history) >= 2:
            previous_day = date.fromisoformat(history[-2]["date"])
            if (latest_day - previous_day).days <= 7:
                periods["1D"] = usd_million(latest_balance - float(history[-2]["balance_idr_trillion"]))
        if len(history) >= 6:
            baseline = history[-6]
            baseline_day = date.fromisoformat(baseline["date"])
            if (latest_day - baseline_day).days <= 11:
                periods["1W"] = usd_million(latest_balance - float(baseline["balance_idr_trillion"]))
        period_starts = {
            "MtD": latest_day.replace(day=1),
            "QtD": latest_day.replace(month=((latest_day.month - 1) // 3) * 3 + 1, day=1),
            "YtD": latest_day.replace(month=1, day=1),
        }
        for key, start in period_starts.items():
            baseline = _balance_at_or_before(history, start - timedelta(days=1))
            if baseline:
                periods[key] = usd_million(latest_balance - float(baseline["balance_idr_trillion"]))
    missing = [key for key, value in periods.items() if value is None]
    note = (
        "Obligasi memakai perubahan posisi kepemilikan SBN rupiah yang dapat diperdagangkan oleh nonresiden dari DJPPR "
        "sebagai proksi arus bersih, bukan data transaksi pasar sekunder. Perubahan posisi dikonversi ke USD juta "
        "dengan kurs USD/IDR pada tanggal observasi terakhir periode. 1W membandingkan posisi lima sesi terakhir."
    )
    if latest_day:
        note += f" Data terakhir per {latest_day.isoformat()}."
    if missing:
        note += f" Periode belum dihitung karena seri pembanding belum lengkap: {', '.join(missing)}."
    if errors:
        note += " Pembaruan sumber terbaru gagal; data historis tersimpan mungkin digunakan."
    return {
        "unit": "USD juta", "periods": periods,
        "availability": "available" if not missing and not errors else "partial" if history else "unavailable",
        "availability_note": note if history else ("Data posisi SBN nonresiden DJPPR belum dapat diakses." + (f" {errors[0]}" if errors else "")),
        "date": latest_day.isoformat() if latest_day else None,
        "history": history[-420:],
        "source": "DJPPR — Kepemilikan SBN Rupiah oleh Non Residen",
        "source_url": DJPPR_PAGE_URL,
        "errors": errors[:5],
    }


def fetch_capital_flow(market_snapshot: dict[str, Any]) -> dict[str, Any]:
    """Fetch daily foreign equity flows and SBN nonresident holdings changes.

    Source caches live in the runtime data directory so worker refreshes do not
    repeatedly download immutable historical months and DJPPR PDF attachments.
    """
    today = _today()
    fx_rates = _usd_idr_by_date(market_snapshot)
    stock = _idx_stock_flow(fx_rates, today)
    bond_history, bond_errors, _source_date = _djppr_holdings_history(today)
    bond = _bond_reading(bond_history, fx_rates, bond_errors)
    return {"Saham": stock, "Obligasi": bond}
