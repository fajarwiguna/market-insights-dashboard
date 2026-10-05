"""Compact, report-version-bound charts used in the one-page PDF."""

from __future__ import annotations

from datetime import date
from math import isfinite
from typing import Any

from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.pdfbase.pdfmetrics import stringWidth
from reportlab.platypus import Flowable, Paragraph, Table, TableStyle


INK = colors.HexColor("#172033")
BODY = colors.HexColor("#475569")
MUTED = colors.HexColor("#64748b")
GRID = colors.HexColor("#e5e7eb")
SBN = colors.HexColor("#e53935")
UST = colors.HexColor("#1e5bff")
SPREAD = colors.HexColor("#43a047")
GOLD = colors.HexColor("#f59e0b")
BORDER = colors.HexColor("#e2e8f0")


def _pick(data: Any, *needles: str, exclude: tuple[str, ...] = ()) -> dict:
    if not isinstance(data, dict):
        return {}
    for key, value in data.items():
        name = str(key).lower()
        if all(needle.lower() in name for needle in needles) and not any(
            item.lower() in name for item in exclude
        ):
            return value if isinstance(value, dict) else {}
    return {}


def _iso_day(value: Any) -> str | None:
    raw = str(value or "")[:10]
    try:
        return date.fromisoformat(raw).isoformat()
    except ValueError:
        return None


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
        return number if isfinite(number) else None
    except (TypeError, ValueError):
        return None


def _read_history(points: Any) -> dict[str, float]:
    result = {}
    for point in points if isinstance(points, list) else []:
        if not isinstance(point, dict):
            continue
        day = _iso_day(point.get("date") or point.get("dates"))
        value = _finite(point.get("close"))
        if day and value is not None:
            result[day] = value
    return result


def _source_snapshot(report: dict) -> dict:
    snapshot = report.get("_source_snapshot")
    return snapshot if isinstance(snapshot, dict) else {}


def _five_dates(series: list[dict[str, float]]) -> list[str]:
    return sorted(set().union(*(set(item) for item in series)))[-5:]


def _asof(points: dict[str, float], day: str) -> float | None:
    if day in points:
        return points[day]
    prior = [key for key in points if key <= day]
    if prior:
        return points[max(prior)]
    future = [key for key in points if key > day]
    return points[min(future)] if future else None


def _date_label(day: str) -> str:
    return f"{day[8:10]}/{day[5:7]}"


def _format_index(value: float) -> str:
    return f"{round(value):,}".replace(",", ".")


def chart_heading(title: str) -> Table:
    """Judul miring dengan sorotan amber seperti contoh dashboard."""
    font_name = "Helvetica-BoldOblique"
    font_size = 13.2
    style = ParagraphStyle(
        f"PdfChartHeading{title.replace(' ', '')}",
        fontName=font_name,
        fontSize=font_size,
        leading=15.4,
        textColor=INK,
    )
    width = stringWidth(title, font_name, font_size) + 5
    heading = Table([[Paragraph(title, style)]], colWidths=[width], hAlign="LEFT")
    heading.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, -1), colors.HexColor("#f7b955")),
        ("LEFTPADDING", (0, 0), (-1, -1), 1.5),
        ("RIGHTPADDING", (0, 0), (-1, -1), 3.5),
        ("TOPPADDING", (0, 0), (-1, -1), 0.5),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 0.5),
    ]))
    return heading


class RateDifferentialChart(Flowable):
    """SBN/UST yields as lines and their spread as bars on a second axis."""

    def __init__(self, report: dict, height: float = 31 * mm):
        super().__init__()
        self.report = report
        self.height = height
        self.width = 0

    def _data(self) -> tuple[list[str], list[float | None], list[float | None]]:
        report = self.report
        snapshot = _source_snapshot(report)
        nested_history = snapshot.get("_sbn_history")
        sbn_rows = report.get("_sbn_history")
        if not isinstance(sbn_rows, list):
            sbn_rows = nested_history if isinstance(nested_history, list) else []
        sbn = _read_history(sbn_rows)
        ust = _read_history(report.get("history_ust10"))
        report_day = _iso_day(report.get("report_date_iso"))
        yfinance = snapshot.get("yfinance")
        yfinance = yfinance if isinstance(yfinance, dict) else {}

        sbn_today = _pick(report.get("yields"), "sbn", "10", exclude=("sbsn", "fr0"))
        ust_today = _pick(report.get("yields"), "treasury", "10")
        sbn_day = _iso_day(sbn_today.get("date")) or report_day
        ust_day = _iso_day((yfinance.get("US10Y") or {}).get("date")) or report_day
        sbn_value = _finite(sbn_today.get("today"))
        ust_value = _finite(ust_today.get("today"))
        if sbn_day and sbn_value is not None:
            sbn[sbn_day] = sbn_value
        if ust_day and ust_value is not None:
            ust[ust_day] = ust_value

        dates = _five_dates([sbn, ust])
        if not dates:
            return [], [], []
        return dates, [_asof(sbn, day) for day in dates], [_asof(ust, day) for day in dates]

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        dates, sbn, ust = self._data()
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setFillColor(colors.white)
        canvas.roundRect(0, 0, self.width, self.height, 4, stroke=1, fill=1)

        if not dates:
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica-Oblique", 7.5)
            canvas.drawCentredString(self.width / 2, self.height / 2,
                                     "Riwayat SBN/UST belum tersedia pada versi laporan ini.")
            canvas.restoreState()
            return

        pairs = [(s, u) for s, u in zip(sbn, ust) if s is not None and u is not None]
        if not pairs:
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica-Oblique", 7.5)
            canvas.drawCentredString(self.width / 2, self.height / 2,
                                     "Riwayat SBN/UST belum tersedia pada versi laporan ini.")
            canvas.restoreState()
            return

        spreads = [(s - u) * 100 if s is not None and u is not None else None
                   for s, u in zip(sbn, ust)]

        def bounds(values, minimum_padding):
            valid = [value for value in values if value is not None]
            low, high = min(valid), max(valid)
            padding = max((high - low) * 0.16, minimum_padding)
            return low - padding, high + padding

        sbn_low, sbn_high = bounds(sbn, 0.025)
        ust_low, ust_high = bounds(ust, 0.025)
        spread_values = [value for value in spreads if value is not None]
        spread_low = max(0, min(spread_values) - 10)
        spread_high = max(spread_values) + 12
        if spread_high <= spread_low:
            spread_high = spread_low + 1

        left, right = 37, self.width - 34
        bottom, top = 25, self.height - 20
        plot_h, plot_w = top - bottom, right - left
        xs = [left + plot_w * i / max(len(dates) - 1, 1) for i in range(len(dates))]

        # Map each yield to its own axis so both lines remain readable.
        for x, spread in zip(xs, spreads):
            if spread is None:
                continue
            bar_top = bottom + (spread - spread_low) / (spread_high - spread_low) * plot_h
            canvas.setFillColor(colors.HexColor("#d8efd9"))
            canvas.setStrokeColor(SPREAD)
            canvas.setLineWidth(0.55)
            canvas.rect(x - 6.5, bottom, 13, max(0.5, bar_top - bottom), stroke=1, fill=1)

        canvas.setFont("Helvetica", 6.2)
        for fraction in (0, 0.5, 1):
            y = bottom + plot_h * fraction
            sbn_tick = sbn_low + (sbn_high - sbn_low) * fraction
            ust_tick = ust_low + (ust_high - ust_low) * fraction
            canvas.setStrokeColor(GRID)
            canvas.setLineWidth(0.45)
            canvas.line(left, y, right, y)
            canvas.setFillColor(MUTED)
            canvas.drawRightString(left - 4, y - 2, f"{sbn_tick:.2f}%".replace(".", ","))
            canvas.drawString(right + 4, y - 2, f"{ust_tick:.2f}%".replace(".", ","))

        for values, low, high, color in ((sbn, sbn_low, sbn_high, SBN), (ust, ust_low, ust_high, UST)):
            valid = [(xs[i], value) for i, value in enumerate(values) if value is not None]
            if len(valid) > 1:
                path = canvas.beginPath()
                for i, (x, value) in enumerate(valid):
                    y = bottom + (value - low) / (high - low) * plot_h
                    if i == 0:
                        path.moveTo(x, y)
                    else:
                        path.lineTo(x, y)
                canvas.setStrokeColor(color)
                canvas.setLineWidth(1.8)
                canvas.drawPath(path, stroke=1, fill=0)
            canvas.setFillColor(color)
            for x, value in valid:
                y = bottom + (value - low) / (high - low) * plot_h
                canvas.circle(x, y, 2, stroke=0, fill=1)

        # Compact legend for the half-page chart column.
        legend_y = self.height - 9
        legend_items = [("SBN 10Y", SBN), ("UST 10Y", UST), ("Spread (bps)", SPREAD)]
        canvas.setFont("Helvetica", 6.2)
        item_widths = [18 + stringWidth(label, "Helvetica", 6.2) for label, _ in legend_items]
        gap = 7
        legend_x = (self.width - sum(item_widths) - gap * (len(legend_items) - 1)) / 2
        for (label, color), item_width in zip(legend_items, item_widths):
            canvas.setStrokeColor(color)
            canvas.setFillColor(colors.HexColor("#f3f4f6") if color == SPREAD else colors.white)
            canvas.setLineWidth(1.4)
            canvas.rect(legend_x, legend_y - 1.5, 12, 6, stroke=1, fill=1)
            canvas.setFillColor(BODY)
            canvas.drawString(legend_x + 16, legend_y, label)
            legend_x += item_width + gap

        for index, (x, day) in enumerate(zip(xs, dates)):
            label = _date_label(day)
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 5.9)
            canvas.drawCentredString(x, 7, label)
            spread = spreads[index]
            if spread is not None:
                canvas.setFillColor(colors.white)
                canvas.setStrokeColor(colors.HexColor("#c9e4cb"))
                canvas.roundRect(x - 13, bottom + 1, 26, 8, 2.5, stroke=1, fill=1)
                canvas.setFillColor(colors.HexColor("#21833b"))
                canvas.setFont("Helvetica-Bold", 5.6)
                canvas.drawCentredString(x, bottom + 3.1, f"{spread:.0f} bp")

        canvas.saveState()
        canvas.translate(9, (bottom + top) / 2)
        canvas.rotate(90)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.4)
        canvas.drawCentredString(0, 0, "SBN 10Y (%)")
        canvas.restoreState()
        canvas.saveState()
        canvas.translate(self.width - 2, (bottom + top) / 2)
        canvas.rotate(90)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.4)
        canvas.drawCentredString(0, 0, "UST 10Y (%)")
        canvas.restoreState()
        canvas.restoreState()


class GoldPricesChart(Flowable):
    """Gold Spot and Antam 1 g prices with independent axes."""

    def __init__(self, report: dict, height: float = 31 * mm):
        super().__init__()
        self.report = report
        self.height = height
        self.width = 0

    def _data(self) -> tuple[list[str], list[float | None], list[float | None]]:
        report = self.report
        snapshot = _source_snapshot(report)
        yfinance = snapshot.get("yfinance")
        yfinance = yfinance if isinstance(yfinance, dict) else {}
        quote = yfinance.get("GOLD")
        quote = quote if isinstance(quote, dict) else {}
        gold_points = _read_history(quote.get("history"))
        gold_reading = _pick(report.get("commodities"), "gold", exclude=("antam",))
        gold_today = _finite(gold_reading.get("today"))
        gold_day = _iso_day(quote.get("date")) or _iso_day(gold_reading.get("date")) \
            or _iso_day(report.get("report_date_iso"))
        if gold_day and gold_today is not None:
            gold_points[gold_day] = gold_today

        antam_points = _read_history(
            report.get("_antam_gold_history") or snapshot.get("_antam_gold_history")
        )
        antam_reading = _pick(report.get("commodities"), "emas", "antam")
        antam_today = _finite(antam_reading.get("today"))
        antam_day = _iso_day(antam_reading.get("date")) or _iso_day(report.get("report_date_iso"))
        if antam_day and antam_today is not None:
            antam_points[antam_day] = antam_today

        dates = sorted(set(gold_points) | set(antam_points))[-5:]
        return dates, [gold_points.get(day) for day in dates], [antam_points.get(day) for day in dates]

    @staticmethod
    def _bounds(values: list[float | None], min_padding: float) -> tuple[float, float]:
        finite = [value for value in values if value is not None]
        low, high = min(finite), max(finite)
        padding = max((high - low) * 0.14, min_padding)
        return low - padding, high + padding

    @staticmethod
    def _draw_series(canvas, xs, values, low, high, bottom, plot_h, color):
        segment = []
        for x, value in zip(xs, values):
            if value is None:
                if len(segment) > 1:
                    path = canvas.beginPath()
                    path.moveTo(*segment[0])
                    for point in segment[1:]:
                        path.lineTo(*point)
                    canvas.setStrokeColor(color)
                    canvas.setLineWidth(1.9)
                    canvas.drawPath(path, stroke=1, fill=0)
                segment = []
                continue
            y = bottom + (value - low) / (high - low) * plot_h
            segment.append((x, y))
        if len(segment) > 1:
            path = canvas.beginPath()
            path.moveTo(*segment[0])
            for point in segment[1:]:
                path.lineTo(*point)
            canvas.setStrokeColor(color)
            canvas.setLineWidth(1.9)
            canvas.drawPath(path, stroke=1, fill=0)
        canvas.setFillColor(color)
        for x, value in zip(xs, values):
            if value is not None:
                y = bottom + (value - low) / (high - low) * plot_h
                canvas.circle(x, y, 2.1, stroke=0, fill=1)

    def wrap(self, availWidth, availHeight):
        self.width = availWidth
        return self.width, self.height

    def draw(self):
        canvas = self.canv
        dates, gold_values, antam_values = self._data()
        canvas.saveState()
        canvas.setStrokeColor(BORDER)
        canvas.setFillColor(colors.white)
        canvas.roundRect(0, 0, self.width, self.height, 4, stroke=1, fill=1)
        if not dates:
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica-Oblique", 7.5)
            canvas.drawCentredString(self.width / 2, self.height / 2,
                                     "Riwayat harga emas belum tersedia pada versi laporan ini.")
            canvas.restoreState()
            return

        left, right = 39, self.width - 39
        bottom, top = 16, self.height - 15
        plot_h, plot_w = top - bottom, right - left
        gold_valid = [value for value in gold_values if value is not None]
        antam_valid = [value for value in antam_values if value is not None]
        gold_low, gold_high = self._bounds(gold_values, 8) if gold_valid else (0, 1)
        antam_low, antam_high = self._bounds(antam_values, 20000) if antam_valid else (0, 1)
        xs = [left + plot_w * i / max(len(dates) - 1, 1) for i in range(len(dates))]

        canvas.setFont("Helvetica", 6.2)
        for fraction in (0, 0.5, 1):
            y = bottom + plot_h * fraction
            canvas.setStrokeColor(GRID)
            canvas.setLineWidth(0.45)
            canvas.line(left, y, right, y)
            canvas.setFillColor(MUTED)
            if gold_valid:
                value = gold_low + (gold_high - gold_low) * fraction
                canvas.drawRightString(left - 4, y - 2, _format_index(value))
            if antam_valid:
                value = antam_low + (antam_high - antam_low) * fraction
                canvas.drawString(right + 4, y - 2, _format_index(value))

        if gold_valid:
            self._draw_series(canvas, xs, gold_values, gold_low, gold_high, bottom, plot_h, GOLD)
        if antam_valid:
            self._draw_series(canvas, xs, antam_values, antam_low, antam_high, bottom, plot_h, SPREAD)

        for x, day in zip(xs, dates):
            canvas.setFillColor(MUTED)
            canvas.setFont("Helvetica", 6.3)
            canvas.drawCentredString(x, 5, _date_label(day))

        legend_y = self.height - 8
        legend_start = max(left, (self.width - 190) / 2)
        canvas.setStrokeColor(GOLD)
        canvas.setLineWidth(1.7)
        canvas.line(legend_start, legend_y, legend_start + 14, legend_y)
        canvas.setFillColor(GOLD)
        canvas.circle(legend_start + 7, legend_y, 1.8, stroke=0, fill=1)
        canvas.setFillColor(BODY)
        canvas.setFont("Helvetica", 6.7)
        canvas.drawString(legend_start + 18, legend_y - 2, "Gold Spot $/Oz")
        antam_legend_x = legend_start + 104
        canvas.setStrokeColor(SPREAD)
        canvas.line(antam_legend_x, legend_y, antam_legend_x + 14, legend_y)
        canvas.setFillColor(SPREAD)
        canvas.circle(antam_legend_x + 7, legend_y, 1.8, stroke=0, fill=1)
        canvas.setFillColor(BODY)
        canvas.drawString(antam_legend_x + 18, legend_y - 2, "Emas Antam Rp/Gr")
        canvas.saveState()
        canvas.translate(9, (bottom + top) / 2)
        canvas.rotate(90)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.4)
        canvas.drawCentredString(0, 0, "USD/oz")
        canvas.restoreState()
        canvas.saveState()
        canvas.translate(self.width - 2, (bottom + top) / 2)
        canvas.rotate(90)
        canvas.setFillColor(MUTED)
        canvas.setFont("Helvetica", 6.4)
        canvas.drawCentredString(0, 0, "Rp/gr")
        canvas.restoreState()
        canvas.restoreState()
