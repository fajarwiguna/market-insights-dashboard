"use client";

import { useMemo, useState } from "react";
import type { HistoryPoint } from "@/lib/api/types";

type Series = { id: string; title: string; unit: string; points: HistoryPoint[]; color: string };
type Range = "1m" | "3m" | "6m" | "1y" | "all";

const ranges: { id: Range; label: string; days: number | null }[] = [
  { id: "1m", label: "1B", days: 31 }, { id: "3m", label: "3B", days: 92 },
  { id: "6m", label: "6B", days: 183 }, { id: "1y", label: "1T", days: 366 },
  { id: "all", label: "Semua", days: null },
];
const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });

function LineChart({ series, range }: { series: Series; range: Range }) {
  const data = useMemo(() => {
    const selected = ranges.find((item) => item.id === range)?.days;
    const points = [...series.points].sort((a, b) => a.dates.localeCompare(b.dates));
    if (selected === null || !selected || points.length < 2) return points;
    // Anchor the range to the newest observation, not the current clock. That
    // keeps server and browser renders identical and includes the latest data
    // even when a report is older than the selected range.
    const latestDate = new Date(`${points[points.length - 1].dates}T00:00:00Z`);
    const cutoff = new Date(latestDate);
    cutoff.setUTCDate(cutoff.getUTCDate() - selected);
    const filtered = points.filter((point) => new Date(`${point.dates}T00:00:00Z`) >= cutoff);
    return filtered.length > 1 ? filtered : points.slice(-Math.min(points.length, 30));
  }, [range, series.points]);

  if (data.length < 2) return <div className="chart-empty">Riwayat belum cukup untuk menampilkan grafik.</div>;

  const width = series.id === "sbn-10y" ? 900 : 520;
  const height = 230;
  const left = 85;
  const right = 14;
  const top = 18;
  const bottom = 33;
  const values = data.map((point) => point.close);
  const min = Math.min(...values);
  const max = Math.max(...values);
  const pad = (max - min) * 0.12 || Math.max(Math.abs(max) * 0.01, 0.01);
  const low = min - pad;
  const high = max + pad;
  const x = (index: number) => left + (index / (data.length - 1)) * (width - left - right);
  const y = (value: number) => top + ((high - value) / (high - low)) * (height - top - bottom);
  const path = data.map((point, index) => `${index ? "L" : "M"}${x(index).toFixed(1)},${y(point.close).toFixed(1)}`).join(" ");
  const labels = [...new Set([0, Math.floor((data.length - 1) / 2), data.length - 1])];

  return (
    <div className="chart-canvas">
      <svg viewBox={`0 0 ${width} ${height}`} role="img" aria-label={`Grafik riwayat ${series.title}`}>
        {[0, 1, 2, 3].map((step) => {
          const value = high - ((high - low) * step) / 3;
          const yy = y(value);
          return <g key={step}><line x1={left} x2={width - right} y1={yy} y2={yy} className="chart-gridline" />
            <text x={left - 9} y={yy + 4} textAnchor="end" className="chart-axis-label">{number.format(value)}{series.unit}</text></g>;
        })}
        <path d={path} fill="none" stroke={series.color} strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        {data.map((point, index) => <circle key={`${point.dates}-${index}`} cx={x(index)} cy={y(point.close)} r={data.length < 45 ? 3 : 1.7} fill={series.color}>
          <title>{`${point.dates}: ${number.format(point.close)}${series.unit}`}</title>
        </circle>)}
        {labels.map((index) => <text key={`${data[index].dates}-${index}`} x={x(index)} y={height - 8} textAnchor={index === 0 ? "start" : index === data.length - 1 ? "end" : "middle"} className="chart-axis-label">{data[index].dates}</text>)}
      </svg>
    </div>
  );
}

export function HistoryCharts({ histories }: { histories: Record<string, HistoryPoint[]> }) {
  const [range, setRange] = useState<Range>("6m");
  const series: Series[] = [
    { id: "sbn-10y", title: "SBN 10 Tahun", unit: "%", points: histories["sbn-10y"] ?? [], color: "#198b7b" },
    { id: "usd-idr", title: "USD/IDR", unit: "", points: histories["usd-idr"] ?? [], color: "#bf9653" },
    { id: "ihsg", title: "IHSG", unit: "", points: histories.ihsg ?? [], color: "#557da8" },
  ];

  return (
    <section className="reader-section history-section" id="history" aria-labelledby="history-heading">
      <div className="section-heading"><div><p className="eyebrow">TREN RIWAYAT</p><h2 id="history-heading">Pergerakan Pasar</h2></div>
        <div className="range-control" role="group" aria-label="Rentang grafik">
          {ranges.map((item) => <button type="button" key={item.id} onClick={() => setRange(item.id)} aria-pressed={range === item.id} className={range === item.id ? "selected" : ""}>{item.label}</button>)}
        </div>
      </div>
      <div className="history-grid">{series.map((item) => <article className={`history-card${item.id === "sbn-10y" ? " history-card-featured" : ""}`} key={item.id}>
        <div className="history-card-heading"><h3>{item.title}</h3><span>{item.points.length ? `${item.points.length} observasi` : "Riwayat terbatas"}</span></div>
        <LineChart series={item} range={range} />
        <p className="chart-caption">Sumber riwayat laporan · tanggal mengikuti data yang tersedia.</p>
      </article>)}</div>
    </section>
  );
}
