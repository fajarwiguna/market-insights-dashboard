"use client";

import { useMemo, useState } from "react";
import type { HistoryPoint } from "@/lib/api/types";
import { formatObservationDate } from "@/features/dashboard/report-format";

type Series = {
  id: string;
  title: string;
  unit: string;
  points: HistoryPoint[];
  color: string;
};
type Range = "1m" | "3m" | "6m" | "all";
type RangeOption = { id: Range; label: string; summaryLabel: string; days: number | null };

const ranges: RangeOption[] = [
  { id: "1m", label: "1 bln", summaryLabel: "1 bulan", days: 31 },
  { id: "3m", label: "3 bln", summaryLabel: "3 bulan", days: 92 },
  { id: "6m", label: "6 bln", summaryLabel: "6 bulan", days: 183 },
  { id: "all", label: "Semua", summaryLabel: "seluruh riwayat", days: null },
];
const dayMilliseconds = 24 * 60 * 60 * 1000;
const wholeNumber = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const rateNumber = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const changeNumber = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 1 });

function dateValue(value: string): number {
  return new Date(`${value}T00:00:00Z`).getTime();
}

function cleanPoints(points: HistoryPoint[]): HistoryPoint[] {
  return points
    .filter((point) => Number.isFinite(point.close) && Number.isFinite(dateValue(point.dates)))
    .slice()
    .sort((a, b) => a.dates.localeCompare(b.dates));
}

function rangeAvailable(points: HistoryPoint[], range: RangeOption): boolean {
  if (points.length < 2) return false;
  if (range.days === null) return true;
  return dateValue(points[points.length - 1].dates) - dateValue(points[0].dates) >= range.days * dayMilliseconds;
}

function pointsInRange(points: HistoryPoint[], range: Range): HistoryPoint[] {
  const option = ranges.find((item) => item.id === range);
  if (!option || option.days === null || points.length < 2) return points;
  const newest = dateValue(points[points.length - 1].dates);
  const cutoff = newest - option.days * dayMilliseconds;
  return points.filter((point) => dateValue(point.dates) >= cutoff);
}

function formatValue(value: number | undefined, series: Series): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  return `${(series.id === "sbn-10y" ? rateNumber : wholeNumber).format(value)}${series.unit}`;
}

function formatPeriodChange(data: HistoryPoint[], series: Series): string {
  if (data.length < 2) return "—";
  const first = data[0].close;
  const last = data[data.length - 1].close;
  if (series.id === "sbn-10y") {
    const change = (last - first) * 100;
    return `${change > 0 ? "+" : ""}${changeNumber.format(change)} bp`;
  }
  if (first === 0) return "—";
  const change = ((last / first) - 1) * 100;
  return `${change > 0 ? "+" : ""}${changeNumber.format(change)}%`;
}

function formatAxisDate(value: string): string {
  const date = new Date(`${value}T00:00:00Z`);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("id-ID", {
    day: "numeric",
    month: "short",
    timeZone: "UTC",
  }).format(date);
}

function LineChart({ series, data }: { series: Series; data: HistoryPoint[] }) {
  if (data.length < 2) return <div className="chart-empty">Riwayat belum cukup untuk menampilkan grafik.</div>;

  const width = 1000;
  const height = 280;
  const top = 14;
  const bottom = 258;
  const values = data.map((point) => point.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.12 || Math.max(Math.abs(max) * 0.01, 0.01);
  const low = min - pad;
  const high = max + pad;
  const x = (index: number) => (index / (data.length - 1)) * width;
  const y = (value: number) => top + ((high - value) / (high - low)) * (bottom - top);
  const path = data.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.close).toFixed(1)}`).join(" ");
  const formatAxisValue = series.id === "sbn-10y" ? rateNumber : wholeNumber;
  const ticks = [0, 1, 2, 3].map((step) => ({
    value: high - ((high - low) * step) / 3,
    position: ((top + ((bottom - top) * step) / 3) / height) * 100,
  }));
  const labelIndices = [...new Set([0, 0.25, 0.5, 0.75, 1].map((ratio) => Math.round(ratio * (data.length - 1))))];
  const dateRange = `${formatObservationDate(data[0].dates)} hingga ${formatObservationDate(data[data.length - 1].dates)}`;

  return (
    <div className="chart-canvas">
      <div className="chart-plot">
        <svg viewBox={`0 0 ${width} ${height}`} preserveAspectRatio="none" role="img" aria-label={`Grafik riwayat ${series.title}, ${dateRange}`}>
          <title>{`Pergerakan ${series.title}, ${dateRange}`}</title>
          {ticks.map((tick, index) => {
            const yy = top + ((bottom - top) * index) / 3;
            return <line key={index} x1="0" x2={width} y1={yy} y2={yy} className="chart-gridline" />;
          })}
          <path d={path} fill="none" stroke={series.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
          {data.map((point, index) => <circle key={`${point.dates}-${index}`} cx={x(index)} cy={y(point.close)} r={data.length < 45 ? 4 : 2} fill={series.color}>
            <title>{`${point.dates}: ${formatValue(point.close, series)}`}</title>
          </circle>)}
        </svg>
        <div className="chart-y-labels" aria-hidden="true">
          {ticks.map((tick, index) => <span key={index} className={index === 0 ? "axis-label-first" : index === ticks.length - 1 ? "axis-label-last" : ""} style={{ top: `${tick.position}%` }}>
            {formatAxisValue.format(tick.value)}{series.unit}
          </span>)}
        </div>
      </div>
      <div className="chart-x-labels" aria-hidden="true">
        {labelIndices.map((index) => <span key={`${data[index].dates}-${index}`}>{formatAxisDate(data[index].dates)}</span>)}
      </div>
    </div>
  );
}

export function HistoryCharts({ histories }: { histories: Record<string, HistoryPoint[]> }) {
  const series: Series[] = [
    { id: "usd-idr", title: "USD/IDR", unit: "", points: histories["usd-idr"] ?? [], color: "#bf9653" },
    { id: "ihsg", title: "IHSG", unit: "", points: histories.ihsg ?? [], color: "#557da8" },
    { id: "sbn-10y", title: "SBN 10Y", unit: "%", points: histories["sbn-10y"] ?? [], color: "#198b7b" },
  ];
  const initialSeries = series.find((item) => item.id === "usd-idr" && item.points.length > 1)
    ?? series.find((item) => item.points.length > 1)
    ?? series[0];
  const [activeId, setActiveId] = useState(initialSeries.id);
  const [selectedRange, setSelectedRange] = useState<Range>("1m");
  const activeSeries = series.find((item) => item.id === activeId) ?? series[0];
  const points = useMemo(() => cleanPoints(activeSeries.points), [activeSeries.points]);
  const activeRange = rangeAvailable(points, ranges.find((item) => item.id === selectedRange) ?? ranges[0])
    ? selectedRange
    : ranges.find((item) => rangeAvailable(points, item))?.id ?? "all";
  const data = useMemo(() => pointsInRange(points, activeRange), [points, activeRange]);
  const latest = data[data.length - 1];
  const activeRangeOption = ranges.find((item) => item.id === activeRange) ?? ranges[0];
  const changeLabel = activeRange === "all" ? "Perubahan seluruh riwayat" : `Perubahan ${activeRangeOption.summaryLabel}`;

  return (
    <section className="reader-section history-section" id="history" aria-labelledby="history-heading">
      <div className="section-heading history-heading">
        <div><p className="eyebrow">TREN PASAR</p><h2 id="history-heading">Pergerakan Pasar</h2></div>
        <div className="instrument-switcher" role="group" aria-label="Pilih instrumen grafik">
          {series.map((item) => <button type="button" key={item.id} onClick={() => setActiveId(item.id)} aria-pressed={activeId === item.id} className={activeId === item.id ? "selected" : ""}>
            <span className="instrument-dot" style={{ backgroundColor: item.color }} />{item.title}
          </button>)}
        </div>
      </div>

      <div className="history-toolbar">
        <div className="history-summary" aria-live="polite">
          <div className="history-stat"><span>Nilai terakhir</span><strong>{formatValue(latest?.close, activeSeries)}</strong></div>
          <div className="history-stat"><span>{changeLabel}</span><strong>{formatPeriodChange(data, activeSeries)}</strong></div>
          <div className="history-stat history-stat-observation"><span>Observasi terakhir</span><strong>{latest ? formatObservationDate(latest.dates) : "—"}</strong><small>{data.length} dari {points.length} observasi</small></div>
        </div>
        <div className="range-control" role="group" aria-label="Rentang grafik">
          {ranges.map((item) => {
            const available = rangeAvailable(points, item);
            return <button type="button" key={item.id} onClick={() => setSelectedRange(item.id)} aria-pressed={activeRange === item.id} aria-label={item.id === "all" ? "Semua data" : `${item.summaryLabel} terakhir`} title={available ? item.summaryLabel : `Data ${item.summaryLabel} belum tersedia`} disabled={!available} className={activeRange === item.id ? "selected" : ""}>{item.label}</button>;
          })}
        </div>
      </div>

      <div className="history-panel">
        <LineChart series={activeSeries} data={data} />
      </div>
    </section>
  );
}
