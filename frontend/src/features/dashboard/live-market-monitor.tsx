"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import type { InstrumentReading, LiveMarket, LiveQuote, MarketReport } from "@/lib/api/types";

const displayNames: Record<string, string> = {
  "fx|USD/IDR": "USD/IDR", "fx|EUR/IDR": "EUR/IDR", "fx|CNY/IDR": "CNY/IDR",
  "fx|JPY/IDR": "JPY/IDR", "fx|DXY": "DXY", "indices|IHSG (ID)": "IHSG",
  "indices|DJI (US)": "Dow Jones", "yields|US Treasury 10 Tahun": "UST 10Y",
  "yields|US Treasury 5 Tahun": "UST 5Y", "commodities|Gold (USD/oz)": "Emas",
  "commodities|Emas Antam 1 gr (Rp)": "Emas Antam 1 gr",
  "commodities|Brent Crude": "Brent", "commodities|WTI Crude": "WTI",
};
const number = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const wholeNumber = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const groups = ["fx", "indices", "yields", "commodities"] as const;
const groupNames: Record<(typeof groups)[number], string> = { fx: "Valuta", indices: "Indeks", yields: "Yield", commodities: "Komoditas" };

function snapshotReading(report: MarketReport, key: string): InstrumentReading | null {
  const [section, label] = key.split("|");
  const source = report[section as keyof MarketReport];
  if (!source || typeof source !== "object") return null;
  const entries = Object.entries(source as Record<string, InstrumentReading>);
  const needles = label.toLowerCase().replace(/\s*\([^)]*\)/g, "").split(/\s+/).filter(Boolean);
  return entries.find(([name]) => needles.every((needle) => name.toLowerCase().includes(needle)))?.[1] ?? null;
}

function formatDate(value?: string | null) {
  if (!value) return "waktu tidak tersedia";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("id-ID", { dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Jakarta" }).format(date) + " WIB";
}

function LiveQuoteCard({ quote, fallback, keyName }: { quote?: LiveQuote; fallback: InstrumentReading | null; keyName: string }) {
  const available = quote?.status === "available" && typeof quote.last === "number";
  const value = available ? quote?.last : fallback?.today;
  const change = available ? quote?.change_pct : fallback?.change_pct;
  const unit = keyName.startsWith("yields|") ? "%" : "";
  const sourceDate = available ? quote?.dates : fallback?.date;
  const origin = available ? "Live" : "Snapshot laporan";
  return <article className={`live-card ${available ? "live-card-fresh" : "live-card-fallback"}`}>
    <div className="live-card-title"><strong>{displayNames[keyName] || keyName}</strong><span>{origin}</span></div>
    <p className="live-value">{typeof value === "number" ? `${(unit ? number : wholeNumber).format(value)}${unit}` : "—"}</p>
    <div className="live-card-meta"><span>{typeof change === "number" ? `${change > 0 ? "+" : ""}${number.format(change)}%` : "Perubahan —"}</span><span>{formatDate(sourceDate)}</span></div>
  </article>;
}

export function LiveMarketMonitor({ report }: { report: MarketReport }) {
  const [data, setData] = useState<LiveMarket | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const activeRequest = useRef<AbortController | null>(null);

  const refresh = useCallback(async () => {
    activeRequest.current?.abort();
    const controller = new AbortController();
    activeRequest.current = controller;
    try {
      const response = await fetch("/api/market/live", { cache: "no-store", signal: controller.signal });
      if (!response.ok) throw new Error("Harga live belum dapat dimuat.");
      const payload = await response.json() as LiveMarket;
      if (controller.signal.aborted) return;
      setData(payload);
      setError("");
    } catch {
      if (controller.signal.aborted) return;
      setData(null);
      setError("Sumber live tidak merespons. Nilai snapshot laporan tetap ditampilkan sebagai cadangan.");
    } finally {
      if (!controller.signal.aborted) setLoading(false);
    }
  }, []);

  useEffect(() => {
    const initialTimer = window.setTimeout(() => void refresh(), 0);
    const timer = window.setInterval(() => { setLoading(true); void refresh(); }, 60_000);
    return () => { window.clearTimeout(initialTimer); window.clearInterval(timer); activeRequest.current?.abort(); };
  }, [refresh]);

  const quotes = data?.quotes ?? {};
  return <section className="reader-section live-section" id="live" aria-labelledby="live-heading">
    <div className="section-heading"><div><p className="eyebrow">PEMANTAUAN INTRADAY</p><h2 id="live-heading">Monitor Pasar Live</h2></div>
      <button type="button" className="live-refresh-button" onClick={() => { setLoading(true); void refresh(); }} disabled={loading}>{loading ? "Memuat…" : "Perbarui sekarang"}</button>
    </div>
    <div className={`live-status live-status-${data?.status || (error ? "unavailable" : "loading")}`} role="status" aria-live="polite">
      <span className="live-status-dot" />
      {error || (data?.status === "available" ? "Data live tersedia" : data?.status === "partial" ? "Sebagian sumber live tersedia" : data?.status === "unavailable" ? "Sumber live tidak tersedia. Snapshot ditampilkan bila tersedia" : "Menghubungi sumber live…")}
      {data?.fetched_at ? <span> · diperbarui {formatDate(data.fetched_at)}</span> : null}
    </div>
    {groups.map((group) => {
      const rows = Object.entries(displayNames).filter(([key]) => key.startsWith(`${group}|`));
      return <div className="live-group" key={group}><h3>{groupNames[group]}</h3><div className="live-grid">
        {rows.map(([key]) => <LiveQuoteCard key={key} keyName={key} quote={quotes[key]} fallback={snapshotReading(report, key)} />)}
      </div></div>;
    })}
    <p className="live-footnote">Harga intraday berasal dari Yahoo Finance dan dapat tertunda. Yield SBN mengikuti publikasi harian PHEI, sedangkan harga Antam mengikuti seri harga beli Antam bertanggal.</p>
  </section>;
}
