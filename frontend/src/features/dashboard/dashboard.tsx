import type { HistoryPoint, InstrumentReading, MarketReport } from "@/lib/api/types";
import { StatusPill } from "@/components/status-pill";
import { AppearanceControls } from "@/components/appearance-controls";
import { ExportReportButton } from "@/components/export-report-button";
import { HistoryCharts } from "@/features/dashboard/history-charts";
import { LiveMarketMonitor } from "@/features/dashboard/live-market-monitor";
import { OperatorMenu } from "@/components/operator-menu";
import { DashboardNav } from "@/features/dashboard/dashboard-nav";
import { ReloadPageButton } from "@/components/reload-page-button";
import { MARKET_GROUPS, MarketDataSections } from "@/features/dashboard/market-data-sections";

type MarketMetricSection = "fx" | "indices" | "yields" | "commodities";

const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const wholeNumberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });

function formatValue(value: unknown, section: MarketMetricSection): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (section === "yields") return `${numberFormat.format(value)}%`;
  return wholeNumberFormat.format(value);
}

function formatChange(reading: InstrumentReading): string {
  const bp = reading.dtd_bp ?? reading.change_bp;
  if (typeof bp === "number" && Number.isFinite(bp)) {
    return `DtD ${bp > 0 ? "+" : ""}${numberFormat.format(bp)} bp`;
  }
  const percent = reading.dtd_pct ?? reading.change_pct;
  if (typeof percent === "number" && Number.isFinite(percent)) {
    return `DtD ${percent > 0 ? "+" : ""}${numberFormat.format(percent)}%`;
  }
  return "DtD —";
}

function findMetric(report: MarketReport, section: MarketMetricSection, fragments: string[]): [string, InstrumentReading] | null {
  const values = report[section];
  if (!values) return null;
  for (const fragment of fragments) {
    const match = Object.entries(values).find(([name]) => name.toLowerCase().includes(fragment.toLowerCase()));
    if (match) return match;
  }
  return null;
}

function formatPublishedAt(value: unknown): string {
  if (typeof value !== "string" || !value) return "Waktu publikasi tidak tersedia";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("id-ID", {
    dateStyle: "medium",
    timeStyle: "short",
    timeZone: "Asia/Jakarta",
  }).format(date) + " WIB";
}

function MetricCard({ title, metric, section }: {
  title: string;
  metric: [string, InstrumentReading] | null;
  section: MarketMetricSection;
}) {
  const [name, reading]: [string, InstrumentReading] = metric ?? ["Data belum tersedia", {}];
  return (
    <article className="metric-card">
      <div className="metric-heading"><span>{title}</span><span>DtD</span></div>
      <p className="metric-name">{name}</p>
      <p className="metric-value">{formatValue(reading.today, section)}</p>
      <p className="metric-change">{formatChange(reading)}</p>
      <p className="metric-date">{reading.availability === "stale" ? "Terakhir tersedia · " : reading.availability === "partial" ? "Sumber alternatif · " : "Tanggal data · "}{reading.date || "tidak tersedia"}</p>
    </article>
  );
}

function MarketReferences({ report }: { report: MarketReport }) {
  const bi = report.bi && typeof report.bi === "object" ? report.bi : {};
  const biRate = bi["BI Rate"];
  const indonia = bi.INDONIA;
  const spread = report.spread_sbn10_ust10_bp;
  const items = [
    { label: "BI Rate", value: typeof biRate === "number" ? `${numberFormat.format(biRate)}%` : "—" },
    { label: "INDONIA", value: typeof indonia === "number" ? `${numberFormat.format(indonia)}%` : "—" },
    { label: "Spread SBN 10Y – UST 10Y", value: typeof spread === "number" ? `${numberFormat.format(spread)} bp` : "—" },
  ];
  return (
    <section className="reference-panel" id="references" aria-label="Indikator acuan">
      <div><p className="eyebrow">MONETARY & SPREAD</p><h2>Indikator acuan</h2></div>
      <div className="reference-items">
        {items.map((item) => <div className="reference-item" key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}
      </div>
    </section>
  );
}

function ReportInsights({ report }: { report: MarketReport }) {
  const insights = report.insights ?? [];
  const impacts = report.impacts ?? [];

  return (
    <>
      <section className="reader-section" id="insights" aria-labelledby="insights-heading">
        <div className="section-heading"><div><p className="eyebrow">RINGKASAN & ANALISIS</p><h2 id="insights-heading">Insight Hari Ini</h2></div></div>
        <p className="summary-copy">{report.summary || "Data hari ini belum lengkap untuk menyusun ringkasan otomatis."}</p>
        {insights.length ? <div className="insight-grid">{insights.slice(0, 3).map((item, index) => (
          <article className={`insight-card tone-${item.tone || "flat"}`} key={`${item.title || "insight"}-${index}`}>
            <h3>{item.title || "Sorotan pasar"}</h3><p>{item.text || "—"}</p>
            {item.dampak && <small><strong>Implikasi:</strong> {item.dampak}</small>}
          </article>
        ))}</div> : <p className="empty-section">Belum ada sorotan untuk laporan ini.</p>}
        {insights.length > 3 && <details className="reader-disclosure additional-insights">
          <summary>Lihat {insights.length - 3} sorotan lainnya</summary>
          <div className="insight-grid">{insights.slice(3).map((item, index) => (
            <article className={`insight-card tone-${item.tone || "flat"}`} key={`${item.title || "insight"}-${index}`}>
              <h3>{item.title || "Sorotan pasar"}</h3><p>{item.text || "—"}</p>
              {item.dampak && <small><strong>Implikasi:</strong> {item.dampak}</small>}
            </article>
          ))}</div>
        </details>}
      </section>

      <section className="reader-section" id="impacts" aria-labelledby="impacts-heading">
        <details className="reader-disclosure" data-section-disclosure>
        <summary><span className="eyebrow">KONTEKS PASAR</span><h2 id="impacts-heading">Implikasi Praktis</h2><span className="disclosure-hint">Buka penjelasan dampak pasar</span></summary>
        {impacts.length ? <div className="impact-grid">{impacts.map((item, index) => (
          <article className="impact-card" key={`${item.title || "impact"}-${index}`}><h3>{item.title || "Dampak praktis"}</h3><p>{item.text || "—"}</p></article>
        ))}</div> : <p className="empty-section">Dampak praktis belum tersedia untuk laporan ini.</p>}
        </details>
      </section>
    </>
  );
}

export function Dashboard({ report, histories = {} }: { report: MarketReport; histories?: Record<string, HistoryPoint[]> }) {
  const featured = [
    { title: "Rupiah", section: "fx" as const, fragments: ["USD/IDR"] },
    { title: "IHSG", section: "indices" as const, fragments: ["IHSG"] },
    { title: "SBN 10Y", section: "yields" as const, fragments: ["ID SBN 10 Tahun", "ID SBN 10Y"] },
    { title: "UST 10Y", section: "yields" as const, fragments: ["US Treasury 10 Tahun", "US Treasury 10Y"] },
    { title: "Emas Antam", section: "commodities" as const, fragments: ["Emas Antam"] },
  ];
  const published = report.published_at || report.generated_at;
  const navigation = [
    { id: "overview", label: "Ringkasan", icon: "◫" },
    { id: "references", label: "Indikator acuan", icon: "⌁" },
    { id: "insights", label: "Insight", icon: "✳" },
    { id: "impacts", label: "Dampak", icon: "⌁" },
    ...(!report.is_demo ? [{ id: "history", label: "Grafik historis", icon: "⌁" }] : []),
    ...MARKET_GROUPS.map((group) => ({ id: group.id, label: group.title, icon: "◦" })),
    ...(!report.is_demo ? [{ id: "live", label: "Monitor live", icon: "◉" }] : []),
  ];

  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="Market Today beranda">
          <span className="brand-mark">M</span><span>market<span className="brand-light">today</span></span>
        </a>
        <p className="sidebar-label">JELAJAHI PASAR</p>
        <DashboardNav items={navigation} />
        <div className="sidebar-bottom"><span className="sidebar-orb" />
          <p>Daily Market Report</p><small>Informasi pasar harian</small>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar"><span>DAILY MARKET INTELLIGENCE</span><div className="topbar-actions"><StatusPill demo={report.is_demo} /><AppearanceControls />{!report.is_demo && <OperatorMenu />}</div></header>
        <section className="page-intro">
          <div><p className="eyebrow">PASAR KEUANGAN · INDONESIA & GLOBAL</p>
            <h1>Market <span>Today</span></h1>
            <p className="intro-copy">Ringkasan pergerakan pasar dalam satu tampilan.</p>
          </div>
          <div className="report-date"><span>TANGGAL LAPORAN</span><strong>{report.report_date || report.report_date_iso || "—"}</strong>
            <small>Dipublikasikan {formatPublishedAt(published)}</small><ExportReportButton reportId={report.report_id} /></div>
        </section>

        <section className="metrics-grid" aria-label="Angka utama">
          {featured.map((item) => <MetricCard key={item.title} title={item.title} section={item.section} metric={findMetric(report, item.section, item.fragments)} />)}
        </section>

        <MarketReferences report={report} />
        <ReportInsights report={report} />
        {!report.is_demo && <HistoryCharts histories={histories} />}
        <MarketDataSections report={report} />
        {!report.is_demo && <LiveMarketMonitor report={report} />}

        <footer className="page-footer"><span>Market Today · Daily Market Report</span>
          <span>ID laporan: {report.report_id || "belum tersedia"}</span></footer>
      </main>
    </div>
  );
}

export function DashboardUnavailable({ message }: { message: string }) {
  return <main className="unavailable-page"><div className="unavailable-card">
    <span className="brand-mark">M</span><p className="eyebrow">MARKET TODAY</p>
    <h1>Laporan belum dapat ditampilkan.</h1><p>{message}</p>
    <ReloadPageButton />
  </div></main>;
}
