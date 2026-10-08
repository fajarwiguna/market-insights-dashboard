"""Pure period aggregation for inbound international equity flows."""
from datetime import date, timedelta
import math

COUNTRIES = ("China", "Japan", "Malaysia", "United States")

def _number(value):
    return value if isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) else None


def foreign_flow_rows(payload: dict, as_of: str) -> list[dict]:
    """Aggregate only complete calendar periods, bounded to the report date."""
    rows = []
    for country in COUNTRIES:
        series = payload.get(country) or {}
        observations = [point for point in series.get("observations") or [] if point.get("date", "9999") <= as_of
                        and _number(point.get("usd_mn")) is not None]
        row = {"country": country, "date": None, "daily": None, "wtd": None, "mtd": None,
               "qtd": None, "ytd": None, "12m": None, "latest": None,
               **{key: series.get(key) for key in ("frequency", "source", "source_url", "methodology")},
               "availability": "unavailable"}
        if not observations:
            rows.append(row)
            continue
        observations.sort(key=lambda point: point["date"])
        latest = observations[-1]
        day = date.fromisoformat(latest["date"])
        frequency = series.get("frequency")
        row.update(date=day.isoformat(), latest=round(latest["usd_mn"], 2),
                   period_start=latest["start"], availability="partial", fetch_failed=series.get("fetch_failed", False))
        if frequency in ("monthly", "quarterly"):
            step = 1 if frequency == "monthly" else 3
            lookup = {point["start"]: point["usd_mn"] for point in observations}
            def total(first: date, last: date):
                values = []
                cursor = first
                while cursor <= last:
                    value = lookup.get(cursor.isoformat())
                    if value is None:
                        return None
                    values.append(value)
                    month_index = cursor.year * 12 + cursor.month - 1 + step
                    cursor = date(month_index // 12, month_index % 12 + 1, 1)
                return round(sum(values), 2) if values else None
            last_start = date.fromisoformat(latest["start"])
            row["mtd"] = row["latest"] if frequency == "monthly" else None
            row["qtd"] = total(date(day.year, ((day.month - 1) // 3) * 3 + 1, 1), last_start)
            row["ytd"] = total(date(day.year, 1, 1), last_start)
            index = last_start.year * 12 + last_start.month - 1 - (12 - step)
            row["12m"] = total(date(index // 12, index % 12 + 1, 1), last_start)
        elif frequency == "daily":
            row["daily"] = row["latest"]
            for key, start in (("wtd", day - timedelta(days=day.weekday())),
                               ("mtd", day.replace(day=1)),
                               ("qtd", date(day.year, ((day.month - 1) // 3) * 3 + 1, 1)),
                               ("ytd", date(day.year, 1, 1))):
                # Require coverage back to the first weekday of the period.
                first = start + timedelta(days=1) if start.weekday() == 6 else start + timedelta(days=2) if start.weekday() == 5 else start
                if observations[0]["date"] <= first.isoformat():
                    selected = [point for point in observations if start.isoformat() <= point["date"] <= day.isoformat()]
                    row[key] = round(sum(point["usd_mn"] for point in selected), 2) if selected else None
        rows.append(row)
    return rows
