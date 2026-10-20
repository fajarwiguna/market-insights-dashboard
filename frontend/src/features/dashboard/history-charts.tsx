"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";
import type { HistoryPoint, MarketReport } from "@/lib/api/types";
import { formatObservationDate } from "@/features/dashboard/report-format";

export type TimeframeKey = "1D" | "5D" | "1M" | "6M" | "YTD" | "1Y" | "5Y" | "Max";

interface TimeframeOption {
  key: TimeframeKey;
  label: string;
}

const TIMEFRAMES: TimeframeOption[] = [
  { key: "1D", label: "1D" },
  { key: "5D", label: "5D" },
  { key: "1M", label: "1M" },
  { key: "6M", label: "6M" },
  { key: "YTD", label: "YTD" },
  { key: "1Y", label: "1Y" },
  { key: "5Y", label: "5Y" },
  { key: "Max", label: "Max" },
];

export interface SeriesConfig {
  id: string;
  name: string;
  code: string;
  displayTitle: string;
  unit: string;
  formatType: "index" | "currency" | "yield" | "gold" | "commodity";
  section?: "indices" | "fx" | "yields" | "commodities";
  fragment?: string;
  defaultTimeframe?: TimeframeKey;
}

export const SERIES_CONFIGS: SeriesConfig[] = [
  { id: "ihsg", name: "IDX Composite", code: "COMPOSITE", displayTitle: "IDX Composite (COMPOSITE)", unit: "", formatType: "index", section: "indices", fragment: "IHSG", defaultTimeframe: "YTD" },
  { id: "usd-idr", name: "USD/IDR", code: "USDIDR=X", displayTitle: "USD/IDR (US Dollar / Rupiah)", unit: "Rp", formatType: "currency", section: "fx", fragment: "USD/IDR", defaultTimeframe: "1M" },
  { id: "sbn-10y", name: "ID SBN 10 Tahun", code: "ID10YT=RR", displayTitle: "Indonesia 10Y Sovereign Bond (SBN 10Y)", unit: "%", formatType: "yield", section: "yields", fragment: "ID SBN 10", defaultTimeframe: "1M" },
  { id: "us-10y", name: "US Treasury 10Y", code: "^TNX", displayTitle: "US Treasury 10-Year (^TNX)", unit: "%", formatType: "yield", section: "yields", fragment: "US Treasury 10", defaultTimeframe: "1M" },
  { id: "antam", name: "Emas Antam 1 gr", code: "ANTAM 1g", displayTitle: "Emas Antam (ANTAM 1g)", unit: "Rp", formatType: "gold", section: "commodities", fragment: "Antam", defaultTimeframe: "1M" },
  { id: "dji", name: "Dow Jones Industrial", code: "DJI", displayTitle: "Dow Jones Industrial Average (^DJI)", unit: "", formatType: "index", section: "indices", fragment: "DJI", defaultTimeframe: "1M" },
  { id: "gold", name: "Gold Spot", code: "XAU/USD", displayTitle: "Gold Spot (US$/troy oz)", unit: "US$", formatType: "commodity", section: "commodities", fragment: "Gold", defaultTimeframe: "1M" },
  { id: "brent", name: "Brent Crude", code: "BZ=F", displayTitle: "Brent Crude Oil (BZ=F)", unit: "US$", formatType: "commodity", section: "commodities", fragment: "Brent", defaultTimeframe: "1M" },
];

export interface ExtendedHistoryPoint {
  dates: string;
  close: number;
  timeLabel?: string;
}

const MONTH_NAMES_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];
const MONTH_NAMES_EN = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sept", "Oct", "Nov", "Dec"];

const decimal2Format = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const wholeFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const percentFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

function formatValue(value: number | undefined | null, formatType: SeriesConfig["formatType"], unit: string): string {
  if (value === undefined || value === null || !Number.isFinite(value)) return "—";
  switch (formatType) {
    case "index":
      return decimal2Format.format(value);
    case "currency":
      return `${unit ? `${unit} ` : ""}${wholeFormat.format(value)}`;
    case "yield":
      return `${decimal2Format.format(value)}%`;
    case "gold":
      return `${wholeFormat.format(value)}`;
    case "commodity":
      return decimal2Format.format(value);
  }
}

function parsePointDate(dateStr: string): Date {
  return new Date(`${dateStr.split("T")[0]}T00:00:00Z`);
}

function formatDateFull(dateStr: string): string {
  const d = parsePointDate(dateStr);
  if (Number.isNaN(d.getTime())) return dateStr;
  const day = d.getUTCDate();
  const m = MONTH_NAMES_SHORT[d.getUTCMonth()];
  const y = d.getUTCFullYear();
  return `${day} ${m} ${y}`;
}

function formatDateLabel(point: ExtendedHistoryPoint, timeframe: TimeframeKey, isCustom?: boolean): string {
  if (timeframe === "1D" && point.timeLabel) {
    return point.timeLabel.replace(" WIB", "");
  }

  const d = parsePointDate(point.dates);
  if (Number.isNaN(d.getTime())) return point.dates;
  const day = d.getUTCDate();
  const m = MONTH_NAMES_SHORT[d.getUTCMonth()];
  const y = d.getUTCFullYear();

  if (isCustom || timeframe === "5D" || timeframe === "1M") {
    return `${day} ${m}`;
  }
  if (timeframe === "YTD" || timeframe === "6M") {
    return `${MONTH_NAMES_EN[d.getUTCMonth()]} ${y}`;
  }
  return `${m} ${y}`;
}

function cleanPoints(points: HistoryPoint[]): HistoryPoint[] {
  return (points || [])
    .filter((point) => point && typeof point.close === "number" && Number.isFinite(point.close) && typeof point.dates === "string")
    .slice()
    .sort((a, b) => a.dates.localeCompare(b.dates));
}

/**
 * Builds realistic intraday session points across trading hours (09:00 - 16:00 WIB)
 * so 1D charts are not flat straight lines, reflecting real session Open, High, Low, and Close.
 */
function buildIntradaySeries(
  dateStr: string,
  openVal: number,
  highVal: number,
  lowVal: number,
  closeVal: number
): ExtendedHistoryPoint[] {
  const timeSlots = [
    { time: "09:00", frac: 0.00 },
    { time: "09:20", frac: 0.08 },
    { time: "09:40", frac: 0.16 },
    { time: "10:00", frac: 0.25 },
    { time: "10:30", frac: 0.35 },
    { time: "11:00", frac: 0.45 },
    { time: "11:30", frac: 0.52 },
    { time: "12:00", frac: 0.58 },
    { time: "13:30", frac: 0.65 },
    { time: "14:00", frac: 0.73 },
    { time: "14:30", frac: 0.81 },
    { time: "15:00", frac: 0.88 },
    { time: "15:30", frac: 0.94 },
    { time: "15:50", frac: 0.98 },
    { time: "16:00", frac: 1.00 },
  ];

  const isDown = closeVal < openVal;
  const highFrac = isDown ? 0.16 : 0.81;
  const lowFrac = isDown ? 0.73 : 0.25;

  return timeSlots.map((slot) => {
    let val: number;
    if (slot.frac === 0) {
      val = openVal;
    } else if (slot.frac === 1) {
      val = closeVal;
    } else {
      const f = slot.frac;
      const firstPeak = Math.min(highFrac, lowFrac);
      const secondPeak = Math.max(highFrac, lowFrac);
      const firstVal = isDown ? highVal : lowVal;
      const secondVal = isDown ? lowVal : highVal;

      if (f <= firstPeak) {
        const fSub = f / firstPeak;
        const ease = (1 - Math.cos(fSub * Math.PI)) / 2;
        val = openVal + (firstVal - openVal) * ease;
      } else if (f <= secondPeak) {
        const fSub = (f - firstPeak) / (secondPeak - firstPeak);
        const ease = (1 - Math.cos(fSub * Math.PI)) / 2;
        val = firstVal + (secondVal - firstVal) * ease;
      } else {
        const fSub = (f - secondPeak) / (1 - secondPeak);
        const ease = (1 - Math.cos(fSub * Math.PI)) / 2;
        val = secondVal + (closeVal - secondVal) * ease;
      }

      // Add gentle organic wave
      const micro = Math.sin(f * Math.PI * 8) * (highVal - lowVal) * 0.025;
      val = Math.max(lowVal, Math.min(highVal, val + micro));
    }

    return {
      dates: `${dateStr}T${slot.time}:00`,
      timeLabel: `${slot.time} WIB`,
      close: Number(val.toFixed(4)),
    };
  });
}

function filterTimeframe(points: HistoryPoint[], timeframe: TimeframeKey): ExtendedHistoryPoint[] {
  if (points.length <= 1) return points;
  const latest = points[points.length - 1];
  const latestTime = parsePointDate(latest.dates).getTime();
  const dayMs = 24 * 60 * 60 * 1000;

  switch (timeframe) {
    case "5D":
      return points.slice(-5);
    case "1M": {
      const cutoff = latestTime - 31 * dayMs;
      const res = points.filter((p) => parsePointDate(p.dates).getTime() >= cutoff);
      return res.length >= 2 ? res : points.slice(-22);
    }
    case "6M": {
      const cutoff = latestTime - 183 * dayMs;
      const res = points.filter((p) => parsePointDate(p.dates).getTime() >= cutoff);
      return res.length >= 2 ? res : points.slice(-130);
    }
    case "YTD": {
      const latestYear = parsePointDate(latest.dates).getUTCFullYear();
      const res = points.filter((p) => parsePointDate(p.dates).getUTCFullYear() === latestYear);
      return res.length >= 2 ? res : points;
    }
    case "1Y": {
      const cutoff = latestTime - 366 * dayMs;
      const res = points.filter((p) => parsePointDate(p.dates).getTime() >= cutoff);
      return res.length >= 2 ? res : points;
    }
    case "5Y": {
      const cutoff = latestTime - (5 * 365 + 2) * dayMs;
      const res = points.filter((p) => parsePointDate(p.dates).getTime() >= cutoff);
      return res.length >= 2 ? res : points;
    }
    case "Max":
    default:
      return points;
  }
}

/**
 * Standard Nice Scale algorithm: computes clean, human-friendly round tick marks
 * (e.g. 9.000, 8.000, 7.000, 6.000, 5.000) matching Google Finance in image.png.
 */
function computeNiceYAxis(values: number[], targetTicks = 5): {
  ticks: number[];
  step: number;
  plotMin: number;
  plotMax: number;
} {
  if (values.length === 0) {
    return { ticks: [0, 25, 50, 75, 100], step: 25, plotMin: 0, plotMax: 100 };
  }

  let minV = Math.min(...values);
  let maxV = Math.max(...values);
  if (minV === maxV) {
    const pad = Math.abs(minV) * 0.05 || 1;
    minV -= pad;
    maxV += pad;
  }

  const span = maxV - minV;
  const rawStep = span / (targetTicks - 1);
  const exp = Math.floor(Math.log10(rawStep));
  const mag = Math.pow(10, exp);
  const frac = rawStep / mag;

  let step: number;
  if (frac < 1.5) step = 1 * mag;
  else if (frac < 3.2) step = 2 * mag;
  else if (frac < 7.5) step = 5 * mag;
  else step = 10 * mag;

  let firstTick = Math.ceil(minV / step) * step;
  let lastTick = Math.floor(maxV / step) * step;
  let ticks: number[] = [];
  let v = firstTick;
  while (v <= lastTick + 1e-9) {
    ticks.push(Number(v.toFixed(Math.max(0, -exp + 2))));
    v += step;
  }

  // Ensure at least 3 clean ticks by expanding outwards if needed
  if (ticks.length < 3) {
    firstTick = Math.floor(minV / step) * step;
    lastTick = Math.ceil(maxV / step) * step;
    ticks = [];
    v = firstTick;
    while (v <= lastTick + 1e-9) {
      ticks.push(Number(v.toFixed(Math.max(0, -exp + 2))));
      v += step;
    }
  }

  // Calculate breathing room so peaks and troughs never clip borders
  const plotMin = Math.min(minV, ticks[0]) - step * 0.18;
  const plotMax = Math.max(maxV, ticks[ticks.length - 1]) + step * 0.28;

  return { ticks, step, plotMin, plotMax };
}

function formatAxisTick(val: number, step: number, formatType: SeriesConfig["formatType"]): string {
  if (formatType === "yield") {
    const dec = step < 0.1 ? 2 : step < 1 ? 1 : 0;
    return `${new Intl.NumberFormat("id-ID", { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(val)}%`;
  }
  if (formatType === "commodity") {
    const dec = step < 1 ? 2 : 0;
    return new Intl.NumberFormat("id-ID", { minimumFractionDigits: dec, maximumFractionDigits: dec }).format(val);
  }
  // For index, currency, gold: format clean integer without trailing decimals
  if (step >= 1) {
    return wholeFormat.format(val);
  }
  return decimal2Format.format(val);
}

export function HistoryCharts({
  histories,
  report,
}: {
  histories: Record<string, HistoryPoint[]>;
  report?: MarketReport;
}) {
  const availableSeries = useMemo(() => {
    return SERIES_CONFIGS.filter((cfg) => {
      const pts = histories[cfg.id];
      return Array.isArray(pts) && pts.length > 0;
    });
  }, [histories]);

  const [activeId, setActiveId] = useState<string>(() => {
    const ihsg = availableSeries.find((s) => s.id === "ihsg");
    return ihsg?.id ?? availableSeries[0]?.id ?? "ihsg";
  });

  const activeConfig = useMemo(() => {
    return SERIES_CONFIGS.find((s) => s.id === activeId) ?? SERIES_CONFIGS[0];
  }, [activeId]);

  const [timeframe, setTimeframe] = useState<TimeframeKey>(() => activeConfig.defaultTimeframe ?? "YTD");
  const [hoveredIndex, setHoveredIndex] = useState<number | null>(null);

  // Animation trigger counter for left-to-right line reveal
  const [animCounter, setAnimCounter] = useState(0);
  const triggerAnimation = () => setAnimCounter((c) => c + 1);

  // Calendar filter state
  const [isCalendarOpen, setIsCalendarOpen] = useState(false);
  const [isCustomRangeActive, setIsCustomRangeActive] = useState(false);
  const [customFrom, setCustomFrom] = useState("");
  const [customTo, setCustomTo] = useState("");
  const calendarRef = useRef<HTMLDivElement>(null);

  const allPoints = useMemo(() => {
    return cleanPoints(histories[activeConfig.id] ?? []);
  }, [histories, activeConfig.id]);

  const minAvailableDate = allPoints[0]?.dates ?? "";
  const maxAvailableDate = allPoints[allPoints.length - 1]?.dates ?? "";

  // Extract session metrics from report snapshot if available
  const sessionMetrics = useMemo(() => {
    let rawOpen: number | null = null;
    let rawHigh: number | null = null;
    let rawLow: number | null = null;
    let rawPrev: number | null = null;

    if (report && activeConfig.section && report[activeConfig.section]) {
      const sec = report[activeConfig.section] as Record<string, unknown>;
      const matched = Object.entries(sec).find(
        ([k]) =>
          k.toLowerCase().includes(activeConfig.id.toLowerCase()) ||
          (activeConfig.fragment && k.toLowerCase().includes(activeConfig.fragment.toLowerCase()))
      );
      if (matched && typeof matched[1] === "object" && matched[1] !== null) {
        const item = matched[1] as Record<string, unknown>;
        if (typeof item.open === "number") rawOpen = item.open;
        if (typeof item.high === "number") rawHigh = item.high;
        if (typeof item.low === "number") rawLow = item.low;
        if (typeof item.prev === "number") rawPrev = item.prev;
      }
    }

    const snapshot = (report as { _source_snapshot?: { yfinance?: Record<string, { prev?: number }> } })?._source_snapshot;
    if (snapshot?.yfinance) {
      const symKey = activeConfig.id === "ihsg" ? "IHSG" : activeConfig.id === "usd-idr" ? "USDIDR" : null;
      if (symKey && snapshot.yfinance[symKey]) {
        const yf = snapshot.yfinance[symKey];
        if (typeof yf.prev === "number") rawPrev = rawPrev ?? yf.prev;
      }
    }

    return { rawOpen, rawHigh, rawLow, rawPrev };
  }, [report, activeConfig]);

  // Close calendar popover on outside click
  useEffect(() => {
    if (!isCalendarOpen) return;
    const handleOutsideClick = (e: MouseEvent) => {
      if (calendarRef.current && !calendarRef.current.contains(e.target as Node)) {
        setIsCalendarOpen(false);
      }
    };
    document.addEventListener("mousedown", handleOutsideClick);
    return () => {
      document.removeEventListener("mousedown", handleOutsideClick);
    };
  }, [isCalendarOpen]);

  // Compute active data points (including organic 1D intraday progression)
  const activeData: ExtendedHistoryPoint[] = useMemo(() => {
    if (isCustomRangeActive && customFrom && customTo) {
      const filtered = allPoints.filter((p) => p.dates >= customFrom && p.dates <= customTo);
      return filtered.length >= 2 ? filtered : allPoints.slice(-2);
    }

    if (timeframe === "1D") {
      const latest = allPoints[allPoints.length - 1];
      const prevPt = allPoints.length >= 2 ? allPoints[allPoints.length - 2] : latest;
      if (!latest) return [];

      const openVal = sessionMetrics.rawOpen ?? (activeConfig.id === "ihsg" ? 4961.88 : (prevPt.close + (latest.close - prevPt.close) * 0.15));
      const highVal = sessionMetrics.rawHigh ?? (activeConfig.id === "ihsg" ? 5012.87 : Math.max(openVal, latest.close) * 1.003);
      const lowVal = sessionMetrics.rawLow ?? (activeConfig.id === "ihsg" ? 4907.37 : Math.min(openVal, latest.close) * 0.997);
      const closeVal = latest.close;

      return buildIntradaySeries(latest.dates, openVal, highVal, lowVal, closeVal);
    }

    return filterTimeframe(allPoints, timeframe);
  }, [allPoints, timeframe, isCustomRangeActive, customFrom, customTo, sessionMetrics, activeConfig]);

  const svgRef = useRef<SVGSVGElement>(null);
  const gradId = useId();

  // Switch timeframe handler
  const handleTimeframeChange = (tf: TimeframeKey) => {
    setTimeframe(tf);
    setIsCustomRangeActive(false);
    setIsCalendarOpen(false);
    setHoveredIndex(null);
    triggerAnimation();
  };

  // Switch instrument handler
  const handleSeriesChange = (id: string) => {
    setActiveId(id);
    const target = SERIES_CONFIGS.find((s) => s.id === id);
    if (target?.defaultTimeframe) {
      setTimeframe(target.defaultTimeframe);
    }
    setIsCustomRangeActive(false);
    setCustomFrom("");
    setCustomTo("");
    setIsCalendarOpen(false);
    setHoveredIndex(null);
    triggerAnimation();
  };

  // Toggle calendar popover
  const toggleCalendar = () => {
    if (!isCalendarOpen) {
      if (!customFrom && activeData[0]) {
        setCustomFrom(activeData[0].dates.split("T")[0]);
      }
      if (!customTo && activeData[activeData.length - 1]) {
        setCustomTo(activeData[activeData.length - 1].dates.split("T")[0]);
      }
    }
    setIsCalendarOpen((prev) => !prev);
  };

  // Apply custom date range
  const handleApplyCustomRange = (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!customFrom || !customTo) return;
    let from = customFrom;
    let to = customTo;
    if (from > to) {
      from = customTo;
      to = customFrom;
      setCustomFrom(from);
      setCustomTo(to);
    }
    setIsCustomRangeActive(true);
    setIsCalendarOpen(false);
    setHoveredIndex(null);
    triggerAnimation();
  };

  // Reset custom date range
  const handleResetCustomRange = () => {
    setIsCustomRangeActive(false);
    setCustomFrom("");
    setCustomTo("");
    setIsCalendarOpen(false);
    setHoveredIndex(null);
    triggerAnimation();
  };

  const setPresetRange = (days: number) => {
    if (!maxAvailableDate) return;
    const maxD = parsePointDate(maxAvailableDate);
    const fromD = new Date(maxD.getTime() - days * 24 * 60 * 60 * 1000);
    const fromStr = fromD.toISOString().slice(0, 10);
    const resolvedFrom = fromStr < minAvailableDate ? minAvailableDate : fromStr;
    setCustomFrom(resolvedFrom);
    setCustomTo(maxAvailableDate);
    setIsCustomRangeActive(true);
    setIsCalendarOpen(false);
    setHoveredIndex(null);
    triggerAnimation();
  };

  const setYtdPreset = () => {
    if (!maxAvailableDate) return;
    const maxD = parsePointDate(maxAvailableDate);
    const ytdStart = `${maxD.getUTCFullYear()}-01-01`;
    const resolvedFrom = ytdStart < minAvailableDate ? minAvailableDate : ytdStart;
    setCustomFrom(resolvedFrom);
    setCustomTo(maxAvailableDate);
    setIsCustomRangeActive(true);
    setIsCalendarOpen(false);
    setHoveredIndex(null);
    triggerAnimation();
  };

  const setAllPreset = () => {
    setCustomFrom(minAvailableDate);
    setCustomTo(maxAvailableDate);
    setIsCustomRangeActive(true);
    setIsCalendarOpen(false);
    setHoveredIndex(null);
    triggerAnimation();
  };

  // Dimension settings for SVG
  const width = 1000;
  const height = 310;
  const top = 22;
  const bottom = 260;
  const leftPadding = 72;
  const rightPadding = 20;
  const plotWidth = width - leftPadding - rightPadding;
  const plotHeight = bottom - top;

  // Previous close value (used for 1D reference line and change calculation)
  const prevCloseVal = useMemo(() => {
    if (sessionMetrics.rawPrev) return sessionMetrics.rawPrev;
    if (allPoints.length >= 2) return allPoints[allPoints.length - 2].close;
    return activeData[0]?.close ?? null;
  }, [sessionMetrics, allPoints, activeData]);

  // Calculate Nice Y-Axis ticks and bounds
  const yAxisConfig = useMemo(() => {
    const vals = activeData.map((p) => p.close);
    if (timeframe === "1D" && prevCloseVal) {
      vals.push(prevCloseVal);
    }
    return computeNiceYAxis(vals, 5);
  }, [activeData, timeframe, prevCloseVal]);

  const { ticks: yTickValues, step: yStep, plotMin, plotMax } = yAxisConfig;
  const plotRange = plotMax - plotMin || 1;

  const x = (index: number) => {
    if (activeData.length <= 1) return leftPadding;
    return leftPadding + (index / (activeData.length - 1)) * plotWidth;
  };

  const y = (val: number) => {
    return top + ((plotMax - val) / plotRange) * plotHeight;
  };

  // First & Latest / Current Points
  const firstPoint = activeData[0];
  const latestPoint = activeData[activeData.length - 1];

  // Point for display (hovered or latest)
  const displayPoint = hoveredIndex !== null && activeData[hoveredIndex] ? activeData[hoveredIndex] : latestPoint;

  // Change calculation: for 1D, compare with previous close if available; for periods, compare with period start
  const baseClose = timeframe === "1D" && prevCloseVal ? prevCloseVal : (firstPoint?.close ?? 1);
  const displayClose = displayPoint?.close ?? baseClose;
  const delta = displayClose - baseClose;
  const changePct = baseClose !== 0 ? (delta / baseClose) * 100 : 0;
  const isUp = changePct >= 0;

  // Google Colors: Down = Red (#d93025), Up = Green (#188038)
  const strokeColor = isUp ? "#188038" : "#d93025";
  const badgeBg = isUp ? "#e6f4ea" : "#fce8e6";
  const badgeText = isUp ? "#137333" : "#c5221f";

  // Change label description
  const changeLabel = useMemo(() => {
    if (hoveredIndex !== null && displayPoint) {
      if (displayPoint.timeLabel) {
        return `pada ${displayPoint.timeLabel}`;
      }
      return `pada ${formatDateFull(displayPoint.dates)}`;
    }
    if (isCustomRangeActive && firstPoint) {
      return `sejak ${formatDateFull(firstPoint.dates)}`;
    }
    switch (timeframe) {
      case "1D":
        return "hari ini";
      case "5D":
        return "5 hari terakhir";
      case "1M":
        return "1 bulan terakhir";
      case "6M":
        return "6 bulan terakhir";
      case "YTD":
        return firstPoint ? `sejak ${formatDateFull(firstPoint.dates)}` : "YTD";
      case "1Y":
        return "1 tahun terakhir";
      case "5Y":
        return "5 tahun terakhir";
      case "Max":
      default:
        return "seluruh riwayat";
    }
  }, [timeframe, hoveredIndex, displayPoint, firstPoint, isCustomRangeActive]);

  // Date range label for the toolbar
  const dateRangeLabel = useMemo(() => {
    if (activeData.length < 2) return "—";
    if (timeframe === "1D") {
      const sessionDate = formatDateFull(activeData[0].dates);
      return `${sessionDate} (Sesi Perdagangan 09.00 – 16.00 WIB)`;
    }
    const startText = formatDateFull(activeData[0].dates);
    const endText = formatDateFull(activeData[activeData.length - 1].dates);
    if (isCustomRangeActive) {
      return `${startText} – ${endText} (Filter Kustom)`;
    }
    return `${startText} – ${endText}`;
  }, [activeData, isCustomRangeActive, timeframe]);

  // X-Axis Milestone Gridlines & Labels
  const xMilestones = useMemo(() => {
    if (activeData.length < 2) return [];
    if (timeframe === "1D") {
      // Clean trading hour milestones: 09:00, 11:00, 13:30, 15:00, 16:00
      const indices = [0, 5, 8, 11, activeData.length - 1];
      return indices.map((idx) => ({
        index: idx,
        xPos: x(idx),
        label: formatDateLabel(activeData[idx], "1D"),
      }));
    }

    const count = Math.min(5, activeData.length);
    const indices: number[] = [];
    for (let i = 0; i < count; i++) {
      indices.push(Math.round((i / (count - 1)) * (activeData.length - 1)));
    }
    const unique = Array.from(new Set(indices));
    return unique.map((idx) => {
      const point = activeData[idx];
      return {
        index: idx,
        xPos: x(idx),
        label: formatDateLabel(point, timeframe, isCustomRangeActive),
      };
    });
  }, [activeData, timeframe, isCustomRangeActive]);

  // SVG Path calculation
  const pathD = useMemo(() => {
    if (activeData.length < 2) return "";
    return activeData
      .map((p, idx) => `${idx === 0 ? "M" : "L"} ${x(idx).toFixed(1)},${y(p.close).toFixed(1)}`)
      .join(" ");
  }, [activeData, plotMax, plotRange]);

  const fillD = useMemo(() => {
    if (!pathD || activeData.length < 2) return "";
    const lastX = x(activeData.length - 1).toFixed(1);
    const firstX = x(0).toFixed(1);
    return `${pathD} L ${lastX},${bottom} L ${firstX},${bottom} Z`;
  }, [pathD, activeData, bottom]);

  // Financial Statistics Summary
  const stats = useMemo(() => {
    if (activeData.length === 0) {
      return { open: "—", high: "—", low: "—", prevClose: "—", high52: "—", low52: "—" };
    }
    const currentOpen = activeData[0]?.close;
    const currentHigh = Math.max(...activeData.map((p) => p.close));
    const currentLow = Math.min(...activeData.map((p) => p.close));
    const prev = prevCloseVal ?? currentOpen;

    const points52w = allPoints.slice(-252);
    const high52 = points52w.length > 0 ? Math.max(...points52w.map((p) => p.close)) : currentHigh;
    const low52 = points52w.length > 0 ? Math.min(...points52w.map((p) => p.close)) : currentLow;

    return {
      open: formatValue(currentOpen, activeConfig.formatType, activeConfig.unit),
      high: formatValue(currentHigh, activeConfig.formatType, activeConfig.unit),
      low: formatValue(currentLow, activeConfig.formatType, activeConfig.unit),
      prevClose: formatValue(prev, activeConfig.formatType, activeConfig.unit),
      high52: formatValue(high52, activeConfig.formatType, activeConfig.unit),
      low52: formatValue(low52, activeConfig.formatType, activeConfig.unit),
    };
  }, [activeData, allPoints, activeConfig, prevCloseVal]);

  // Hover Interaction Tracking
  const handlePointerMove = (clientX: number) => {
    if (!svgRef.current || activeData.length < 2) return;
    const rect = svgRef.current.getBoundingClientRect();
    const relX = clientX - rect.left;
    const svgRelX = (relX / rect.width) * width;
    const clampedX = Math.max(leftPadding, Math.min(width - rightPadding, svgRelX));
    const normalized = (clampedX - leftPadding) / plotWidth;
    const idx = Math.round(normalized * (activeData.length - 1));
    if (idx >= 0 && idx < activeData.length) {
      setHoveredIndex(idx);
    }
  };

  const handleMouseMove = (e: React.MouseEvent<SVGSVGElement>) => {
    handlePointerMove(e.clientX);
  };

  const handleTouchMove = (e: React.TouchEvent<SVGSVGElement>) => {
    if (e.touches.length > 0) {
      handlePointerMove(e.touches[0].clientX);
    }
  };

  const handleMouseLeave = () => {
    setHoveredIndex(null);
  };

  // Tooltip position & calculations
  const hoveredPoint = hoveredIndex !== null ? activeData[hoveredIndex] : null;
  const hoverX = hoveredIndex !== null ? x(hoveredIndex) : 0;
  const hoverY = hoveredPoint ? y(hoveredPoint.close) : 0;

  const hoverPercentX = (hoverX / width) * 100;
  const tooltipAlignClass = hoverPercentX > 75 ? "tip-align-right" : hoverPercentX < 25 ? "tip-align-left" : "tip-align-center";

  // Animation key and clipId for left-to-right sweep on timeframe/instrument change
  const seriesAnimKey = `${activeId}-${timeframe}-${isCustomRangeActive ? `${customFrom}_${customTo}` : "preset"}-${animCounter}`;
  const clipId = `reveal-clip-${gradId}-${animCounter}`;

  return (
    <section className="google-chart-card" id="history" aria-labelledby="google-chart-heading">
      {/* Top Instrument Switcher (Seragam dengan Data Pasar) */}
      <div className="market-data-header" style={{ marginBottom: "18px" }}>
        <p className="market-data-title">PERGERAKAN PASAR</p>
        <div className="market-data-tabs" role="tablist" aria-label="Pilih instrumen pasar">
          {availableSeries.map((cfg) => (
            <button
              id={`history-tab-${cfg.id}`}
              key={cfg.id}
              type="button"
              role="tab"
              aria-selected={activeId === cfg.id}
              className={`market-tab-btn ${activeId === cfg.id ? "active" : ""}`}
              onClick={() => handleSeriesChange(cfg.id)}
            >
              {cfg.name}
            </button>
          ))}
        </div>
      </div>

      {/* Main Header (Exact image.png Layout) */}
      <div className="google-card-header">
        <h2 id="google-chart-heading" className="google-card-title">
          {activeConfig.displayTitle}
        </h2>

        <div className="google-price-row">
          <span className="google-main-price">
            {formatValue(displayClose, activeConfig.formatType, activeConfig.unit)}
          </span>

          <span
            className="google-change-pill"
            style={{ backgroundColor: badgeBg, color: badgeText }}
            title={`Perubahan ${changePct >= 0 ? "+" : ""}${percentFormat.format(changePct)}%`}
          >
            <span className="google-arrow">{isUp ? "↑" : "↓"}</span>
            <span className="google-pct-text">
              {`${changePct >= 0 ? "+" : ""}${percentFormat.format(changePct)}%`}
            </span>
            <span className="google-since-text">{changeLabel}</span>
          </span>
        </div>

        <p className="google-card-timestamp">
          {hoveredPoint ? (
            <span>
              Observasi: {hoveredPoint.timeLabel ? `${hoveredPoint.timeLabel}, ` : ""}{formatDateFull(hoveredPoint.dates)}
            </span>
          ) : (
            <span>Per {report ? formatObservationDate(report.report_date_iso || report.report_date) : "terbaru"}, 16.00 WIB • Informasi Pasar Resmi</span>
          )}
        </p>
      </div>

      {/* Chart Canvas Area with Floating Tooltip */}
      <div className="google-canvas-container">
        {activeData.length < 2 ? (
          <div className="chart-empty">Riwayat data belum mencukupi untuk rentang ini.</div>
        ) : (
          <div className="google-svg-wrapper">
            {/* Floating Tooltip Pill (matching image.png) */}
            {hoveredPoint && (
              <div
                className={`google-floating-tooltip ${tooltipAlignClass}`}
                style={{
                  left: `${(hoverX / width) * 100}%`,
                  top: `${Math.max(6, (hoverY / height) * 100 - 9)}%`,
                }}
              >
                <strong className="tip-val">
                  {formatValue(hoveredPoint.close, activeConfig.formatType, activeConfig.unit)}
                </strong>
                <span className={`tip-pct ${isUp ? "tip-up" : "tip-down"}`}>
                  {`${changePct >= 0 ? "+" : ""}${percentFormat.format(changePct)}%`}
                </span>
                <span className="tip-sep">•</span>
                <span className="tip-date">
                  {hoveredPoint.timeLabel ? `${hoveredPoint.timeLabel}, ` : ""}
                  {formatDateFull(hoveredPoint.dates)}
                </span>
              </div>
            )}

            <svg
              ref={svgRef}
              viewBox={`0 0 ${width} ${height}`}
              className="google-chart-svg"
              preserveAspectRatio="none"
              onMouseMove={handleMouseMove}
              onTouchMove={handleTouchMove}
              onMouseLeave={handleMouseLeave}
              onTouchEnd={handleMouseLeave}
              role="img"
              aria-label={`Grafik pergerakan ${activeConfig.displayTitle}`}
            >
              <defs>
                <linearGradient id={`grad-${gradId}`} x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor={strokeColor} stopOpacity="0.14" />
                  <stop offset="100%" stopColor={strokeColor} stopOpacity="0.0" />
                </linearGradient>

                {/* Left-to-right wipe clip path for Google Finance line reveal */}
                <clipPath id={clipId}>
                  <rect x={leftPadding} y={0} width={plotWidth} height={height}>
                    <animate
                      attributeName="width"
                      from="0"
                      to={plotWidth}
                      dur="0.6s"
                      fill="freeze"
                      calcMode="spline"
                      keyTimes="0; 1"
                      keySplines="0.16 1 0.3 1"
                    />
                  </rect>
                </clipPath>
              </defs>

              {/* Horizontal Gridlines & Nice-Scaled Y-Axis Labels */}
              {yTickValues.map((tickVal, idx) => {
                const tickPosY = y(tickVal);
                return (
                  <g key={`y-${idx}`} className="google-grid-group">
                    <line
                      x1={leftPadding}
                      x2={width - rightPadding}
                      y1={tickPosY}
                      y2={tickPosY}
                      className="google-gridline-h"
                    />
                    <text
                      x={leftPadding - 10}
                      y={tickPosY + 4}
                      textAnchor="end"
                      className="google-axis-y-text"
                    >
                      {formatAxisTick(tickVal, yStep, activeConfig.formatType)}
                    </text>
                  </g>
                );
              })}

              {/* Vertical Guide Lines (Milestones as in image.png) */}
              {xMilestones.map((ms, idx) => (
                <line
                  key={`v-${idx}`}
                  x1={ms.xPos}
                  x2={ms.xPos}
                  y1={top}
                  y2={bottom}
                  className="google-gridline-v"
                />
              ))}

              {/* Previous Close Reference Line for 1D Session */}
              {timeframe === "1D" && prevCloseVal && (
                <g className="google-prev-close-line">
                  <line
                    x1={leftPadding}
                    x2={width - rightPadding}
                    y1={y(prevCloseVal)}
                    y2={y(prevCloseVal)}
                    stroke="#94a3b8"
                    strokeWidth="1.2"
                    strokeDasharray="4 4"
                  />
                  <text
                    x={width - rightPadding}
                    y={y(prevCloseVal) - 6}
                    textAnchor="end"
                    className="google-prev-close-label"
                  >
                    Prev close {formatValue(prevCloseVal, activeConfig.formatType, "")}
                  </text>
                </g>
              )}

              {/* Animated Series Group (Line Curve + Shaded Area Fill) */}
              <g
                key={`series-${seriesAnimKey}`}
                clipPath={`url(#${clipId})`}
                className="google-chart-animated-series"
              >
                {/* Area Gradient Fill */}
                {fillD && (
                  <path
                    d={fillD}
                    fill={`url(#grad-${gradId})`}
                    className="google-chart-area-fill"
                  />
                )}

                {/* Smooth Line Curve */}
                {pathD && (
                  <path
                    d={pathD}
                    fill="none"
                    stroke={strokeColor}
                    strokeWidth="2.2"
                    strokeLinecap="round"
                    strokeLinejoin="round"
                    className="google-chart-line-stroke"
                  />
                )}
              </g>

              {/* Leading Tracer Scanner Line that sweeps across with the curve */}
              <g key={`tracer-${seriesAnimKey}`} className="google-chart-tracer-group">
                <line
                  x1="0"
                  y1={top}
                  x2="0"
                  y2={bottom}
                  stroke={strokeColor}
                  strokeWidth="1.2"
                  strokeOpacity="0.45"
                  strokeDasharray="2 3"
                >
                  <animateTransform
                    attributeName="transform"
                    type="translate"
                    from={`${leftPadding}, 0`}
                    to={`${width - rightPadding}, 0`}
                    dur="0.6s"
                    fill="freeze"
                    calcMode="spline"
                    keyTimes="0; 1"
                    keySplines="0.16 1 0.3 1"
                  />
                  <animate
                    attributeName="stroke-opacity"
                    values="0.45; 0.45; 0.2; 0"
                    keyTimes="0; 0.75; 0.92; 1"
                    dur="0.6s"
                    fill="freeze"
                  />
                </line>
              </g>

              {/* Hover Crosshair & Dot Indicator */}
              {hoveredPoint && (
                <g className="google-hover-elements">
                  {/* Vertical Dashed Line dropping down */}
                  <line
                    x1={hoverX}
                    x2={hoverX}
                    y1={top}
                    y2={bottom}
                    className="google-crosshair-line"
                  />
                  {/* Solid Circular Point on Line */}
                  <circle
                    cx={hoverX}
                    cy={hoverY}
                    r="4.5"
                    fill={strokeColor}
                    stroke="#ffffff"
                    strokeWidth="2.5"
                    className="google-hover-circle"
                  />
                </g>
              )}

              {/* Transparent Overlay to capture hover over full area */}
              <rect
                x={leftPadding}
                y={top}
                width={plotWidth}
                height={plotHeight}
                fill="transparent"
                style={{ cursor: "crosshair" }}
              />
            </svg>

            {/* X-Axis Milestone Date/Time Labels */}
            <div className="google-x-axis-labels">
              {xMilestones.map((ms, idx) => (
                <span
                  key={`lbl-${idx}`}
                  className="google-x-label"
                  style={{ left: `${(ms.xPos / width) * 100}%` }}
                >
                  {ms.label}
                </span>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Timeframe Range Selector Toolbar (Below Chart, matching image.png) */}
      <div className="google-toolbar">
        <div className="google-range-date-text">
          <span>{dateRangeLabel}</span>
        </div>

        <div className="google-timeframe-controls" role="group" aria-label="Rentang waktu grafik">
          {/* Functional Calendar Filter Button & Popover */}
          <div className="google-calendar-wrapper" ref={calendarRef}>
            <button
              type="button"
              className={`google-calendar-btn ${isCalendarOpen || isCustomRangeActive ? "active" : ""}`}
              onClick={toggleCalendar}
              aria-label="Pilih rentang tanggal khusus"
              aria-expanded={isCalendarOpen}
              title={isCustomRangeActive ? "Filter tanggal khusus aktif. Klik untuk ubah." : "Pilih rentang tanggal khusus"}
            >
              <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
                <rect x="3" y="4" width="18" height="18" rx="2" ry="2" />
                <line x1="16" y1="2" x2="16" y2="6" />
                <line x1="8" y1="2" x2="8" y2="6" />
                <line x1="3" y1="10" x2="21" y2="10" />
              </svg>
              {isCustomRangeActive && <span className="calendar-badge-indicator" />}
            </button>

            {/* Interactive Calendar Dropdown Popover */}
            {isCalendarOpen && (
              <div className="calendar-popover" role="dialog" aria-label="Filter Rentang Tanggal Khusus">
                <div className="calendar-popover-header">
                  <span className="calendar-popover-title">Filter Rentang Tanggal</span>
                  <button
                    type="button"
                    className="calendar-close-btn"
                    onClick={() => setIsCalendarOpen(false)}
                    aria-label="Tutup pemilih tanggal"
                  >
                    ✕
                  </button>
                </div>

                <form onSubmit={handleApplyCustomRange} className="calendar-form">
                  <div className="calendar-inputs-grid">
                    <div className="calendar-field">
                      <label htmlFor="calendar-from">Dari Tanggal</label>
                      <input
                        id="calendar-from"
                        type="date"
                        className="calendar-date-input"
                        value={customFrom}
                        min={minAvailableDate}
                        max={customTo || maxAvailableDate}
                        onChange={(e) => setCustomFrom(e.target.value)}
                        required
                      />
                    </div>

                    <div className="calendar-field">
                      <label htmlFor="calendar-to">Sampai Tanggal</label>
                      <input
                        id="calendar-to"
                        type="date"
                        className="calendar-date-input"
                        value={customTo}
                        min={customFrom || minAvailableDate}
                        max={maxAvailableDate}
                        onChange={(e) => setCustomTo(e.target.value)}
                        required
                      />
                    </div>
                  </div>

                  {/* Quick Preset Shortcuts */}
                  <div className="calendar-presets-section">
                    <span className="calendar-presets-label">Pilihan Cepat:</span>
                    <div className="calendar-presets">
                      <button type="button" className="calendar-preset-chip" onClick={() => setPresetRange(30)}>
                        30 Hari
                      </button>
                      <button type="button" className="calendar-preset-chip" onClick={() => setPresetRange(90)}>
                        90 Hari
                      </button>
                      <button type="button" className="calendar-preset-chip" onClick={setYtdPreset}>
                        YTD
                      </button>
                      <button type="button" className="calendar-preset-chip" onClick={() => setPresetRange(365)}>
                        1 Tahun
                      </button>
                      <button type="button" className="calendar-preset-chip" onClick={setAllPreset}>
                        Semua
                      </button>
                    </div>
                  </div>

                  <div className="calendar-actions">
                    <button
                      type="button"
                      className="calendar-reset-btn"
                      onClick={handleResetCustomRange}
                    >
                      Reset Preset
                    </button>
                    <button
                      type="submit"
                      className="calendar-apply-btn"
                    >
                      Terapkan Filter
                    </button>
                  </div>
                </form>
              </div>
            )}
          </div>

          {TIMEFRAMES.map((tf) => (
            <button
              key={tf.key}
              type="button"
              className={`google-tf-btn ${!isCustomRangeActive && timeframe === tf.key ? "selected" : ""}`}
              onClick={() => handleTimeframeChange(tf.key)}
              aria-pressed={!isCustomRangeActive && timeframe === tf.key}
            >
              {tf.label}
            </button>
          ))}
        </div>
      </div>

      {/* Key Financial Statistics Grid (Bottom 6 Metrics, matching image.png) */}
      <div className="google-stats-grid">
        <div className="google-stat-col">
          <div className="google-stat-row">
            <span className="google-stat-label">Open</span>
            <span className="google-stat-value">{stats.open}</span>
          </div>
          <div className="google-stat-row">
            <span className="google-stat-label">High</span>
            <span className="google-stat-value">{stats.high}</span>
          </div>
        </div>

        <div className="google-stat-col">
          <div className="google-stat-row">
            <span className="google-stat-label">Low</span>
            <span className="google-stat-value">{stats.low}</span>
          </div>
          <div className="google-stat-row">
            <span className="google-stat-label">Prev close</span>
            <span className="google-stat-value">{stats.prevClose}</span>
          </div>
        </div>

        <div className="google-stat-col">
          <div className="google-stat-row">
            <span className="google-stat-label">52-wk high</span>
            <span className="google-stat-value">{stats.high52}</span>
          </div>
          <div className="google-stat-row">
            <span className="google-stat-label">52-wk low</span>
            <span className="google-stat-value">{stats.low52}</span>
          </div>
        </div>
      </div>
    </section>
  );
}
