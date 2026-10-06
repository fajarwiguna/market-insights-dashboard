"""Period comparisons derived from dated observations, never from refresh time."""

from __future__ import annotations

from datetime import date, datetime, timedelta
import math
from typing import Any


def _date(value: Any) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def _points(history: Any) -> list[tuple[date, float]]:
    if not isinstance(history, list):
        return []
    result: dict[date, float] = {}
    for point in history:
        if not isinstance(point, dict):
            continue
        day = _date(point.get("date") or point.get("dates"))
        value = point.get("close")
        if day is None or isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value):
            continue
        result[day] = float(value)
    return sorted(result.items())


def _period_start(day: date, period: str) -> date:
    if period == "wtd":
        return day - timedelta(days=day.weekday())
    if period == "mtd":
        return day.replace(day=1)
    if period == "qtd":
        month = ((day.month - 1) // 3) * 3 + 1
        return day.replace(month=month, day=1)
    return day.replace(month=1, day=1)


def _baseline(points: list[tuple[date, float]], start: date) -> tuple[date, float] | None:
    candidates = [point for point in points if point[0] < start]
    return candidates[-1] if candidates else None


def period_changes(history: Any, as_of: Any, latest: Any = None) -> dict[str, Any]:
    """Return previous observation and WtD/MtD/QtD/YtD returns for a price series.

    Period baselines are the last available observation strictly before the
    calendar period starts. Missing baselines remain null so holidays or short
    histories cannot be mistaken for a zero change.
    """
    points = _points(history)
    day = _date(as_of)
    if day is None:
        day = points[-1][0] if points else None
    if day is None:
        return {
            "prev_date": None,
            "wtd_pct": None,
            "mtd_pct": None,
            "qtd_pct": None,
            "ytd_pct": None,
        }

    eligible = [point for point in points if point[0] <= day]
    latest_point = (day, float(latest)) if isinstance(latest, (int, float)) and not isinstance(latest, bool) else (eligible[-1] if eligible else None)
    previous_point = eligible[-2] if len(eligible) > 1 and eligible[-1][0] == day else (eligible[-1] if eligible and eligible[-1][0] < day else None)

    output: dict[str, Any] = {
        "prev_date": previous_point[0].isoformat() if previous_point else None,
    }
    if latest_point is None:
        for period in ("wtd", "mtd", "qtd", "ytd"):
            output[f"{period}_pct"] = None
        return output

    for period in ("wtd", "mtd", "qtd", "ytd"):
        base = _baseline(points, _period_start(day, period))
        value = latest_point[1]
        output[f"{period}_pct"] = round((value / base[1] - 1) * 100, 4) if base and base[1] else None
    return output


def yield_ytd_bp(history: Any, as_of: Any, latest: Any = None) -> float | None:
    """Return year-to-date yield movement in basis points."""
    points = _points(history)
    day = _date(as_of)
    if day is None:
        day = points[-1][0] if points else None
    if day is None or not points:
        return None
    base = _baseline(points, date(day.year, 1, 1))
    if base is None:
        return None
    current = latest if isinstance(latest, (int, float)) and not isinstance(latest, bool) else next(
        (value for point_day, value in reversed(points) if point_day <= day), None
    )
    if current is None:
        return None
    return round((float(current) - base[1]) * 100, 1)
