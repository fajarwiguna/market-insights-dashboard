"use client";

import { useCallback, useEffect, useId, useRef, useState } from "react";
import type { HistoryPoint, InstrumentReading, LiveMarket, LiveQuote, MarketReport } from "@/lib/api/types";

type GroupKey = "VALUTA" | "INDEKS" | "YIELD" | "KOMODITAS";

interface InstrumentConfig {
  key: string;
  name: string;
  unit: string;
  group: GroupKey;
  historyId: string;
  formatType: "currency" | "index" | "yield" | "commodity";
}

const INSTRUMENTS: InstrumentConfig[] = [
  // VALUTA
  { key: "fx|USD/IDR", name: "USD/IDR", unit: "Rp per unit", group: "VALUTA", historyId: "usd-idr", formatType: "currency" },
  { key: "fx|EUR/IDR", name: "EUR/IDR", unit: "Rp per unit", group: "VALUTA", historyId: "eur-idr", formatType: "currency" },
  { key: "fx|CNY/IDR", name: "CNY/IDR", unit: "Rp per unit", group: "VALUTA", historyId: "cny-idr", formatType: "currency" },
  { key: "fx|JPY/IDR", name: "JPY/IDR", unit: "Rp per unit", group: "VALUTA", historyId: "jpy-idr", formatType: "currency" },
  { key: "fx|DXY", name: "DXY", unit: "Indeks", group: "VALUTA", historyId: "dxy", formatType: "index" },

  // INDEKS
  { key: "indices|IHSG (ID)", name: "IHSG", unit: "Indeks", group: "INDEKS", historyId: "ihsg", formatType: "index" },
  { key: "indices|DJI (US)", name: "Dow Jones", unit: "Indeks", group: "INDEKS", historyId: "dji", formatType: "index" },

  // YIELD
  { key: "yields|US Treasury 10 Tahun", name: "UST 10Y", unit: "%", group: "YIELD", historyId: "us-10y", formatType: "yield" },
  { key: "yields|US Treasury 5 Tahun", name: "UST 5Y", unit: "%", group: "YIELD", historyId: "us-5y", formatType: "yield" },

  // KOMODITAS
  { key: "commodities|Gold (USD/oz)", name: "Emas", unit: "US$/troy oz", group: "KOMODITAS", historyId: "gold", formatType: "commodity" },
  { key: "commodities|Emas Antam 1 gr (Rp)", name: "Emas Antam 1 gr", unit: "Rp/gram", group: "KOMODITAS", historyId: "antam", formatType: "currency" },
  { key: "commodities|Brent Crude", name: "Brent", unit: "US$/barel", group: "KOMODITAS", historyId: "brent", formatType: "commodity" },
  { key: "commodities|WTI Crude", name: "WTI", unit: "US$/barel", group: "KOMODITAS", historyId: "wti", formatType: "commodity" },
];

const GROUPS: GroupKey[] = ["VALUTA", "INDEKS", "YIELD", "KOMODITAS"];

const currencyFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const yieldFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const changeFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });

const MONTHS_SHORT = ["Jan", "Feb", "Mar", "Apr", "Mei", "Jun", "Jul", "Agu", "Sep", "Okt", "Nov", "Des"];

function formatObservationDateTime(dateStr?: string | null): { dateText: string; timeText: string } {
  if (!dateStr) return { dateText: "—", timeText: "—" };

  if (/^\d{4}-\d{2}-\d{2}$/.test(dateStr)) {
    const parts = dateStr.split("-");
    const day = parseInt(parts[2], 10);
    const month = MONTHS_SHORT[parseInt(parts[1], 10) - 1] || parts[1];
    const year = parts[0];
    return { dateText: `${day} ${month} ${year}`, timeText: "07.00 WIB" };
  }

  const d = new Date(dateStr);
  if (Number.isNaN(d.getTime())) {
    return { dateText: dateStr, timeText: "" };
  }

  try {
    const formatted = new Intl.DateTimeFormat("id-ID", {
      timeZone: "Asia/Jakarta",
      day: "numeric",
      month: "short",
      year: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(d);

    const day = formatted.find((p) => p.type === "day")?.value || "";
    const month = formatted.find((p) => p.type === "month")?.value || "";
    const year = formatted.find((p) => p.type === "year")?.value || "";
    const hour = formatted.find((p) => p.type === "hour")?.value || "07";
    const minute = formatted.find((p) => p.type === "minute")?.value || "00";

    return {
      dateText: `${day} ${month} ${year}`,
      timeText: `${hour}.${minute} WIB`,
    };
  } catch {
    return { dateText: dateStr, timeText: "" };
  }
}

function snapshotReading(report: MarketReport, key: string): InstrumentReading | null {
  const [section, label] = key.split("|");
  const source = report[section as keyof MarketReport];
  if (!source || typeof source !== "object") return null;
  const entries = Object.entries(source as Record<string, InstrumentReading>);
  const needles = label.toLowerCase().replace(/\s*\([^)]*\)/g, "").split(/\s+/).filter(Boolean);
  return entries.find(([name]) => needles.every((needle) => name.toLowerCase().includes(needle)))?.[1] ?? null;
}

function Sparkline({
  points,
  tone,
  id,
}: {
  points: number[];
  tone: "positive" | "negative" | "neutral";
  id: string;
}) {
  const width = 130;
  const height = 36;
  const paddingY = 4;
  const paddingX = 2;
  const uniqueId = useId();
  const gradId = `spark-grad-${id}-${uniqueId.replace(/[:]/g, "")}`;

  let pts = points;
  if (!pts || pts.length < 2) {
    if (tone === "positive") {
      pts = [10, 10.2, 10.15, 10.4, 10.35, 10.6, 10.55, 10.8];
    } else if (tone === "negative") {
      pts = [10.8, 10.6, 10.65, 10.4, 10.45, 10.2, 10.25, 10.0];
    } else {
      pts = [10.0, 10.05, 9.98, 10.02, 10.0, 10.04, 9.99, 10.0];
    }
  }

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const pad = (max - min) * 0.1 || Math.max(Math.abs(max) * 0.02, 0.01);
  const low = min - pad;
  const high = max + pad;
  const range = high - low;

  const mapped = pts.map((val, idx) => {
    const x = paddingX + (idx / (pts.length - 1)) * (width - paddingX * 2);
    const y = paddingY + ((high - val) / range) * (height - paddingY * 2);
    return { x, y };
  });

  let pathD = `M ${mapped[0].x.toFixed(1)} ${mapped[0].y.toFixed(1)}`;
  for (let i = 0; i < mapped.length - 1; i++) {
    const p0 = mapped[Math.max(i - 1, 0)];
    const p1 = mapped[i];
    const p2 = mapped[i + 1];
    const p3 = mapped[Math.min(i + 2, mapped.length - 1)];

    const cp1x = p1.x + (p2.x - p0.x) / 6;
    const cp1y = p1.y + (p2.y - p0.y) / 6;
    const cp2x = p2.x - (p3.x - p1.x) / 6;
    const cp2y = p2.y - (p3.y - p1.y) / 6;

    pathD += ` C ${cp1x.toFixed(1)} ${cp1y.toFixed(1)}, ${cp2x.toFixed(1)} ${cp2y.toFixed(1)}, ${p2.x.toFixed(1)} ${p2.y.toFixed(1)}`;
  }

  const fillD = `${pathD} L ${mapped[mapped.length - 1].x.toFixed(1)} ${height} L ${mapped[0].x.toFixed(1)} ${height} Z`;

  const strokeColor =
    tone === "positive" ? "#10B981" : tone === "negative" ? "#EF4444" : "#94A3B8";

  return (
    <svg
      width={width}
      height={height}
      viewBox={`0 0 ${width} ${height}`}
      className="monitor-sparkline"
      preserveAspectRatio="none"
      aria-hidden="true"
    >
      <defs>
        <linearGradient id={gradId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={strokeColor} stopOpacity={tone === "neutral" ? 0.14 : 0.22} />
          <stop offset="100%" stopColor={strokeColor} stopOpacity={0.0} />
        </linearGradient>
      </defs>
      <path d={fillD} fill={`url(#${gradId})`} />
      <path
        d={pathD}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.75"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

export function LiveMarketMonitor({
  report,
  initialHistories = {},
}: {
  report: MarketReport;
  initialHistories?: Record<string, HistoryPoint[]>;
}) {
  const [data, setData] = useState<LiveMarket | null>(null);
  const [loading, setLoading] = useState(false);
  const activeRequest = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    setLoading(true);

    try {
      const response = await fetch("/api/market/live", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Harga live belum dapat dimuat.");
      const payload = (await response.json()) as LiveMarket;
      if (controller.signal.aborted) return;
      setData(payload);
    } catch {
      if (controller.signal.aborted) return;
      setData(null);
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => {
      void refresh();
    }, 60_000);

    return () => {
      window.clearTimeout(initialTimer);
      window.clearInterval(timer);
      activeRequest.current?.abort();
    };
  }, [refresh]);

  const quotes = data?.quotes ?? {};
  const isLiveConnected = data?.status === "available";
  const badgeText = isLiveConnected ? "Data live" : "Snapshot laporan";

  return (
    <section className="market-monitor-card" aria-labelledby="monitor-heading">
      {/* Card Header */}
      <div className="monitor-card-header">
        <div className="monitor-title-area">
          <p className="monitor-eyebrow">PEMANTAUAN PASAR</p>
          <h1 id="monitor-heading" className="monitor-title">Monitor Pasar</h1>
          <p className="monitor-subtitle">Ringkasan valuta, indeks, yield, dan komoditas.</p>
        </div>
        <div className="monitor-actions">
          <span className="monitor-badge">{badgeText}</span>
          <button
            type="button"
            className="monitor-refresh-btn"
            onClick={() => void refresh()}
            disabled={loading}
          >
            <svg
              width="14"
              height="14"
              viewBox="0 0 24 24"
              fill="none"
              stroke="#D97706"
              strokeWidth="2.2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className={loading ? "spin-icon" : ""}
              aria-hidden="true"
            >
              <path d="M21 12a9 9 0 0 0-9-9 9.75 9.75 0 0 0-6.74 2.74L3 8" />
              <path d="M3 3v5h5" />
              <path d="M3 12a9 9 0 0 0 9 9 9.75 9.75 0 0 0 6.74-2.74L21 16" />
              <path d="M16 21h5v-5" />
            </svg>
            <span>{loading ? "Memuat…" : "Perbarui"}</span>
          </button>
        </div>
      </div>

      {/* Alert Status Banner */}
      <div className="monitor-alert" role="status">
        <svg
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="#D97706"
          strokeWidth="2.2"
          strokeLinecap="round"
          strokeLinejoin="round"
          aria-hidden="true"
        >
          <path d="m21.73 18-8-14a2 2 0 0 0-3.48 0l-8 14A2 2 0 0 0 4 21h16a2 2 0 0 0 1.73-3Z" />
          <line x1="12" y1="9" x2="12" y2="13" />
          <line x1="12" y1="17" x2="12.01" y2="17" />
        </svg>
        <span>
          {isLiveConnected
            ? "Data live terhubung dari pasar."
            : "Data live belum tersedia. Menampilkan snapshot laporan."}
        </span>
      </div>

      {/* Main 5-Column Table */}
      <div className="monitor-table-wrap">
        <div className="monitor-table">
          {/* Header Row */}
          <div className="monitor-col-headers" role="row">
            <span>INDIKATOR</span>
            <span>NILAI TERAKHIR</span>
            <span>PERUBAHAN</span>
            <span>TREN 30 HARI*</span>
            <span>PEMBARUAN</span>
          </div>

          {/* Groups & Rows */}
          {GROUPS.map((group) => {
            const items = INSTRUMENTS.filter((inst) => inst.group === group);
            return (
              <div key={group} className="monitor-group-container">
                {/* Group Banner */}
                <div className="monitor-group-bar">
                  <span className="monitor-group-accent" aria-hidden="true" />
                  <span className="monitor-group-title">{group}</span>
                </div>

                {/* Instrument Rows */}
                {items.map((item) => {
                  const fallback = snapshotReading(report, item.key);
                  const quote = quotes[item.key] as LiveQuote | undefined;
                  const isAvailableLive = quote?.status === "available" && typeof quote.last === "number";

                  const rawValue = isAvailableLive ? quote.last : fallback?.today;
                  const rawChange = isAvailableLive ? quote.change_pct : (fallback?.change_pct ?? fallback?.dtd_pct);
                  const rawDate = isAvailableLive ? quote.dates : fallback?.date;

                  // Format Value
                  let formattedValue = "—";
                  if (typeof rawValue === "number" && Number.isFinite(rawValue)) {
                    if (item.formatType === "yield") {
                      formattedValue = `${yieldFormat.format(rawValue)}%`;
                    } else {
                      formattedValue = currencyFormat.format(rawValue);
                    }
                  }

                  // Format Change
                  let changeText = "—";
                  let tone: "positive" | "negative" | "neutral" = "neutral";

                  if (item.formatType === "yield") {
                    changeText = "—";
                    tone = "neutral";
                  } else if (typeof rawChange === "number" && Number.isFinite(rawChange)) {
                    if (Math.abs(rawChange) < 0.001) {
                      changeText = "0,00%";
                      tone = "neutral";
                    } else if (rawChange > 0) {
                      changeText = `+${changeFormat.format(rawChange)}%`;
                      tone = "positive";
                    } else {
                      changeText = `-${changeFormat.format(Math.abs(rawChange))}%`;
                      tone = "negative";
                    }
                  }

                  // 30-day History Points
                  const historySeries = initialHistories[item.historyId] ?? [];
                  const cleanPoints = historySeries
                    .filter((p) => typeof p.close === "number" && Number.isFinite(p.close))
                    .slice(-30)
                    .map((p) => p.close);

                  // Update Date & Time
                  const { dateText, timeText } = formatObservationDateTime(rawDate);

                  return (
                    <div key={item.key} className="monitor-row" role="row">
                      {/* Column 1: Indikator */}
                      <div className="monitor-cell-indicator">
                        <span className="instrument-name">{item.name}</span>
                        <span className="instrument-unit">{item.unit}</span>
                      </div>

                      {/* Column 2: Nilai Terakhir */}
                      <div className="monitor-cell-value">
                        {formattedValue}
                      </div>

                      {/* Column 3: Perubahan */}
                      <div className={`monitor-cell-change change-${tone}`}>
                        {changeText}
                      </div>

                      {/* Column 4: Tren 30 Hari */}
                      <div className="monitor-cell-sparkline">
                        <Sparkline points={cleanPoints} tone={tone} id={item.historyId} />
                      </div>

                      {/* Column 5: Pembaruan */}
                      <div className="monitor-cell-updated">
                        <span className="update-date">{dateText}</span>
                        <span className="update-time">{timeText}</span>
                      </div>
                    </div>
                  );
                })}
              </div>
            );
          })}
        </div>
      </div>

      {/* Footnote */}
      <p className="monitor-footnote">*Grafik ilustratif untuk preview desain, bukan riwayat pasar aktual.</p>
    </section>
  );
}
