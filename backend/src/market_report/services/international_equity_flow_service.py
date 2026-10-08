"""Public inbound portfolio equity flows, with explicit source frequencies."""
from __future__ import annotations

import calendar
import csv
import io
import json
import logging
import math
import re
from concurrent.futures import ThreadPoolExecutor
from datetime import date, datetime, timedelta
from urllib.parse import urljoin
from zipfile import ZipFile
import xml.etree.ElementTree as ET

import requests
from bs4 import BeautifulSoup

from market_report.config import market_data_directory

logger = logging.getLogger(__name__)
JAPAN_URL = "https://www.mof.go.jp/policy/international_policy/reference/itn_transactions_in_securities/week.csv"
US_URL = "https://fred.stlouisfed.org/data/FORLTEQTYNET99996.txt"
CHINA_URL = "https://www.safe.gov.cn/en/2019/0329/1496.html"
MALAYSIA_URL = "https://www.malaysiastock.biz/Market-Statistic.aspx"
COUNTRIES = ("China", "Japan", "Malaysia", "United States")
XML = {"s": "http://schemas.openxmlformats.org/spreadsheetml/2006/main"}


def _number(value):
    try:
        number = float(str(value).strip().replace(",", "").replace("*", "").replace("(", "-").replace(")", ""))
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def _get(url: str) -> bytes:
    response = requests.get(url, headers={"User-Agent": "Mozilla/5.0"}, timeout=20)
    response.raise_for_status()
    return response.content


def parse_us(content: bytes) -> list[dict]:
    """FRED's dated table values are already millions of USD."""
    soup = BeautifulSoup(content, "lxml")
    points = []
    for row in soup.select("tr"):
        cells = [cell.get_text(" ", strip=True) for cell in row.select("th, td")]
        if len(cells) != 2 or not re.fullmatch(r"\d{4}-\d{2}-01", cells[0]):
            continue
        amount = _number(cells[1])
        if amount is not None:
            first = date.fromisoformat(cells[0])
            last = first.replace(day=calendar.monthrange(first.year, first.month)[1])
            points.append({"start": first.isoformat(), "date": last.isoformat(), "usd_mn": amount})
    return points


def parse_japan(content: bytes) -> list[dict]:
    text = content.decode("cp932")
    if "Portfolio Investment Liabilities" not in text or "Unit: 100 million Yen" not in text:
        raise ValueError("MOF series or units changed")
    points = []
    for row in csv.reader(io.StringIO(text)):
        match = re.fullmatch(r"\s*(\d{4})[．.](\d{1,2})[．.](\d{1,2})[～~]\s*(\d{1,2})[．.](\d{1,2})\s*", row[0]) if row else None
        if not match or len(row) < 15:
            continue
        year, month, day, end_month, end_day = map(int, match.groups())
        start = date(year, month, day)
        end = date(year + (end_month < month), end_month, end_day)
        amount = _number(row[14])  # Inbound equity/fund shares NET, not outbound or debt.
        if amount is not None:
            points.append({"start": start.isoformat(), "date": end.isoformat(), "local_mn": amount * 100})
    return points


def parse_china(content: bytes) -> list[dict]:
    """Read SAFE's quarterly USD portfolio equity liabilities, excluding FDI."""
    with ZipFile(io.BytesIO(content)) as workbook:
        strings = ["".join(item.itertext()) for item in ET.fromstring(workbook.read("xl/sharedStrings.xml"))]
        book = ET.fromstring(workbook.read("xl/workbook.xml"))
        sheet = next(item for item in book.findall("s:sheets/s:sheet", XML) if item.get("name") == "quarterly(USD)")
        relationship = sheet.get("{http://schemas.openxmlformats.org/officeDocument/2006/relationships}id")
        relations = ET.fromstring(workbook.read("xl/_rels/workbook.xml.rels"))
        target = next(item.get("Target") for item in relations if item.get("Id") == relationship)
        path = target.lstrip("/") if target.startswith("/") else f"xl/{target}"
        rows = []
        for row in ET.fromstring(workbook.read(path)).findall(".//s:row", XML):
            cells = {}
            for cell in row.findall("s:c", XML):
                value = cell.find("s:v", XML)
                if value is not None:
                    cells[re.sub(r"\d", "", cell.get("r"))] = strings[int(value.text)] if cell.get("t") == "s" else value.text
            rows.append(cells)
        if not any("100 million of US dollars" in row.get("A", "") for row in rows):
            raise ValueError("SAFE USD units unavailable")
        header = next(row for row in rows if any(re.fullmatch(r"\d{4}Q[1-4]", text) for text in row.values()))
        values = next(row for row in rows if row.get("A", "").strip().startswith("2.2.1.2.2.1 Equity and investment fund shares"))
        points = []
        for column, period in header.items():
            match = re.fullmatch(r"(\d{4})Q([1-4])", period)
            amount = _number(values.get(column))
            if match and amount is not None:
                year, quarter = map(int, match.groups())
                month = quarter * 3
                points.append({"start": date(year, month - 2, 1).isoformat(),
                               "date": date(year, month, calendar.monthrange(year, month)[1]).isoformat(),
                               "usd_mn": amount * 100})
        return points


def parse_malaysia(content: bytes) -> list[dict]:
    soup = BeautifulSoup(content, "lxml")
    table = soup.select_one("#MainContent_tbBursaStatistic")
    if table is None or "Foreign" not in table.get_text():
        raise ValueError("Foreign participation table unavailable")
    points = []
    for row in table.select("tr"):
        cells = row.select("td")
        if len(cells) != 7:
            continue
        try:
            day = datetime.strptime(cells[0].get_text(strip=True), "%d %b %Y").date().isoformat()
        except ValueError:
            continue
        # Participation percent is a nested span; never append it to NET value.
        for element in cells[1].select("span"):
            element.decompose()
        amount = _number(cells[1].get_text(strip=True))
        if amount is not None:
            points.append({"start": day, "date": day, "local_mn": amount})
    return points


def _fx(symbol: str) -> list[dict]:
    from market_report.fetch_data import _yahoo_chart
    from market_report.calculate import persist_json_data
    path = market_data_directory() / "international_flow" / f"fx-{symbol.replace('=', '-')}.json"
    reading = _yahoo_chart(symbol, range_="1y")
    if reading.get("history"):
        persist_json_data(reading, path)
    else:
        try:
            reading = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return []
    return reading.get("history") or []


def _fetch(country: str) -> dict:
    root = market_data_directory() / "international_flow"
    root.mkdir(parents=True, exist_ok=True)
    path = root / f"{country.lower().replace(' ', '-')}.json"
    specs = {
        "China": (CHINA_URL, "quarterly", "SAFE", "Portfolio equity and investment fund shares: liabilities, BPM6."),
        "Japan": (JAPAN_URL, "weekly", "MOF Japan", "Inbound equity and investment fund shares, designated major investors. USD uses period-average Yahoo FX."),
        "Malaysia": (MALAYSIA_URL, "daily", "MalaysiaStock.Biz / Bursa preliminary", "Preliminary foreign net trading, excluding amendments. USD uses transaction-date Yahoo FX."),
        "United States": (US_URL, "monthly", "Treasury TIC / FRED", "Foreign net purchases of US equities and fund shares, FORLTEQTYNET99996."),
    }
    url, frequency, provider, methodology = specs[country]
    try:
        if country == "China":
            soup = BeautifulSoup(_get(url), "lxml")
            link = next(a["href"] for a in soup.select("a[href]") if a["href"].lower().endswith(".xlsx"))
            download = urljoin(url, link)
            if not download.startswith("https://www.safe.gov.cn/"):
                raise ValueError("Unexpected SAFE workbook host")
            points = parse_china(_get(download))
        else:
            parser = {"Japan": parse_japan, "Malaysia": parse_malaysia, "United States": parse_us}[country]
            points = parser(_get(url))
        if country in ("Japan", "Malaysia"):
            rates = _fx("JPY=X" if country == "Japan" else "MYR=X")
            for point in points:
                eligible = [rate for rate in rates if point["start"] <= rate.get("date", "") <= point["date"]
                            and _number(rate.get("close")) is not None and rate["close"] > 0]
                if not eligible:
                    continue
                rate = sum(item["close"] for item in eligible) / len(eligible)
                point["usd_mn"] = point["local_mn"] / rate
                point["fx_dates"] = [item["date"] for item in eligible]
        points = [point for point in points if _number(point.get("usd_mn")) is not None]
        if not points:
            raise ValueError("No dated USD flow observations")
        payload = {"country": country, "frequency": frequency, "source": provider, "source_url": url,
                   "methodology": methodology, "retrieved_at": datetime.now().isoformat(),
                   "observations": sorted(points, key=lambda point: point["date"])}
        from market_report.calculate import persist_json_data
        persist_json_data(payload, path)
        return payload
    except Exception:
        logger.warning("Foreign equity flow source unavailable: %s", country, exc_info=True)
        try:
            cached = json.loads(path.read_text(encoding="utf-8"))
            if cached.get("country") == country and cached.get("source_url") == url:
                return {**cached, "fetch_failed": True}
        except (OSError, ValueError, AttributeError):
            pass
        return {"country": country, "frequency": frequency, "source": provider, "source_url": url,
                "methodology": methodology, "observations": [], "fetch_failed": True}


def fetch_international_equity_flows() -> dict:
    with ThreadPoolExecutor(max_workers=4) as pool:
        return {country: payload for country, payload in zip(COUNTRIES, pool.map(_fetch, COUNTRIES))}

