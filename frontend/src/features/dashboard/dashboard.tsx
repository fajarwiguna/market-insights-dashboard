import type { HistoryPoint, InstrumentReading, MarketReport } from "@/lib/api/types";
import { StatusPill } from "@/components/status-pill";
import { AppearanceControls } from "@/components/appearance-controls";
import { ExportReportButton } from "@/components/export-report-button";
import { DashboardViewSwitcher } from "@/features/dashboard/dashboard-view-switcher";
import { HistoryCharts } from "@/features/dashboard/history-charts";
import { OperatorMenu } from "@/components/operator-menu";
import { DashboardNav } from "@/features/dashboard/dashboard-nav";
import { ReloadPageButton } from "@/components/reload-page-button";
import { MarketDataSections } from "@/features/dashboard/market-data-sections";
import { NarrativePanel } from "@/features/dashboard/narrative-panel";
import { TreasuryImplicationsCard } from "@/features/dashboard/treasury-implications-card";
import { formatObservationDate, formatPublishedAt, formatReportDate } from "@/features/dashboard/report-format";

type MarketMetricSection = "fx" | "indices" | "yields" | "commodities";

const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 0 });
const decimalFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const bpFormat = new Intl.NumberFormat("id-ID", { minimumFractionDigits: 0, maximumFractionDigits: 1 });

function formatValue(value: unknown, section: MarketMetricSection): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (section === "yields") return `${decimalFormat.format(value)}%`;
  return numberFormat.format(value);
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

function KpiMiniSparkline({ points, tone = "positive" }: { points: HistoryPoint[]; tone?: "positive" | "negative" | "neutral" }) {
  const width = 76;
  const height = 28;
  const padding = 2;

  const validPoints = points
    .filter((p) => typeof p.close === "number" && Number.isFinite(p.close))
    .slice(-18)
    .map((p) => p.close);

  let pts = validPoints;
  if (pts.length < 2) {
    pts = tone === "negative"
      ? [10.8, 10.6, 10.7, 10.4, 10.5, 10.2, 10.3, 10]
      : [10, 10.2, 10.1, 10.4, 10.3, 10.6, 10.5, 10.8];
  }

  const min = Math.min(...pts);
  const max = Math.max(...pts);
  const pad = (max - min) * 0.1 || Math.max(Math.abs(max) * 0.02, 0.01);
  const low = min - pad;
  const high = max + pad;
  const range = high - low;

  const mapped = pts.map((val, idx) => {
    const x = padding + (idx / (pts.length - 1)) * (width - padding * 2);
    const y = padding + ((high - val) / range) * (height - padding * 2);
    return { x, y };
  });

  const pathD = mapped.map((p, idx) => `${idx === 0 ? "M" : "L"} ${p.x.toFixed(1)} ${p.y.toFixed(1)}`).join(" ");

  return (
    <svg width={width} height={height} viewBox={`0 0 ${width} ${height}`} className="kpi-sparkline" preserveAspectRatio="none" aria-hidden="true">
      <path d={pathD} fill="none" stroke="#C88D2B" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

interface KpiCardConfig {
  title: string;
  subtitle: string;
  section: MarketMetricSection;
  fragments: string[];
  historyId: string;
  isAntam?: boolean;
}

function KpiCard({
  config,
  report,
  history,
}: {
  config: KpiCardConfig;
  report: MarketReport;
  history: HistoryPoint[];
}) {
  const metric = findMetric(report, config.section, config.fragments);
  const reading = metric?.[1] ?? {};

  // Value
  const formattedVal = formatValue(reading.today, config.section);

  // Change
  const bp = reading.dtd_bp ?? reading.change_bp;
  const pct = reading.dtd_pct ?? reading.change_pct;

  let changeText = "—";
  let tone: "positive" | "negative" | "neutral" = "neutral";
  let isUp = true;

  if (typeof bp === "number" && Number.isFinite(bp)) {
    if (Math.abs(bp) >= 0.05) {
      isUp = bp > 0;
      tone = isUp ? "positive" : "negative";
      changeText = `${isUp ? "+" : ""}${bpFormat.format(bp)} bps`;
    } else {
      changeText = "0 bps";
      tone = "neutral";
    }
  } else if (typeof pct === "number" && Number.isFinite(pct)) {
    if (Math.abs(pct) >= 0.005) {
      isUp = pct > 0;
      tone = isUp ? "positive" : "negative";
      changeText = `${isUp ? "+" : ""}${decimalFormat.format(pct)}%`;
    } else {
      changeText = "0,00%";
      tone = "neutral";
    }
  }

  // Observation date
  const obsDate = formatObservationDate(reading.date || report.report_date_iso || report.report_date);

  return (
    <article className="kpi-card">
      <div className="kpi-titles">
        <strong className="kpi-title">{config.title}</strong>
        <span className="kpi-subtitle">{config.subtitle}</span>
      </div>

      <div className="kpi-middle">
        <div className="kpi-values-block">
          <p className="kpi-value">{formattedVal}</p>
          {config.isAntam ? (
            <span className="kpi-subunit">Rp/gram</span>
          ) : (
            <div className={`kpi-change change-${tone}`}>
              {tone !== "neutral" && (
                <span className="kpi-arrow">{isUp ? "▲" : "▼"}</span>
              )}
              <span>{changeText}</span>
            </div>
          )}
        </div>
        <div className="kpi-spark-wrap">
          <KpiMiniSparkline points={history} tone={tone} />
        </div>
      </div>

      <div className="kpi-footer">
        <span className="kpi-obs">Observasi {obsDate}</span>
      </div>
    </article>
  );
}

function ReportInsights({ report }: { report: MarketReport }) {
  const usd = findMetric(report, "fx", ["USD/IDR"])?.[1];
  const ihsg = findMetric(report, "indices", ["IHSG"])?.[1];
  const sbn = findMetric(report, "yields", ["ID SBN 10 Tahun", "ID SBN 10Y", "SBN 10"])?.[1];

  const FLAT_PCT = 0.05;
  const finite = (value: unknown): value is number => typeof value === "number" && Number.isFinite(value);
  const usdChange = finite(usd?.change_pct) ? usd.change_pct : finite(usd?.dtd_pct) ? usd.dtd_pct : null;
  const ihsgChange = finite(ihsg?.change_pct) ? ihsg.change_pct : finite(ihsg?.dtd_pct) ? ihsg.dtd_pct : null;
  const sbnChange = finite(sbn?.dtd_bp) ? sbn.dtd_bp : finite(sbn?.change_bp) ? sbn.change_bp : null;

  const direction = (change: number | null, up: string, down: string) =>
    change === null ? null : change > FLAT_PCT ? up : change < -FLAT_PCT ? down : "stabil";

  // Arah instrument apa adanya (USD/IDR naik, IHSG turun) — tidak menafsirkan rupiah.
  const verb = (change: number | null) => direction(change, "naik", "turun");

  const bullets = [
    finite(usd?.today)
      ? (usdChange === null
        ? `USD/IDR di ${numberFormat.format(usd.today)}.`
        : `USD/IDR ${verb(usdChange)} ${decimalFormat.format(Math.abs(usdChange))}% ke ${numberFormat.format(usd.today)}.`)
      : null,
    finite(ihsg?.today)
      ? (ihsgChange === null
        ? `IHSG di ${numberFormat.format(ihsg.today)}.`
        : `IHSG ${verb(ihsgChange)} ${decimalFormat.format(Math.abs(ihsgChange))}% ke ${numberFormat.format(ihsg.today)}.`)
      : null,
    finite(sbn?.today)
      ? (sbnChange === null
        ? `Yield SBN 10Y di ${decimalFormat.format(sbn.today)}%.`
        : `Yield SBN 10Y ${verb(sbnChange)} ${bpFormat.format(Math.abs(sbnChange))} bps ke ${decimalFormat.format(sbn.today)}%.`)
      : null,
  ].filter((line): line is string => Boolean(line));

  // Judul berasal dari backend (build_headline) bila ada; jika tidak, dihitung dari
  // data yang sama. Rupiah memakai konvensi USD/IDR: kurs naik berarti rupiah melemah.
  const rupiah = direction(usdChange, "melemah", "menguat");
  const derived = [rupiah ? `Rupiah ${rupiah}` : null, direction(ihsgChange, "menguat", "melemah") ? `IHSG ${direction(ihsgChange, "menguat", "melemah")}` : null]
    .filter((part): part is string => Boolean(part))
    .join(", ");
  const headline = (report.headline ?? "").trim() || derived || "Ringkasan Pasar Hari Ini";

  return (
    <div className="insight-treasury-grid">
      {/* Left: Insight Hari Ini */}
      <article className="insight-today-card" id="insights">
        <p className="eyebrow">INSIGHT HARI INI</p>
        <h2 className="insight-headline">{headline}</h2>
        <ul className="insight-bullet-list">
          {bullets.length > 0 ? bullets.map((bullet, idx) => (
            <li key={idx} className="insight-bullet-item">
              <span className="insight-dot" />
              <span>{bullet}</span>
            </li>
          )) : (
            <li className="insight-bullet-item">
              <span className="insight-dot" />
              <span>Data indikator utama belum tersedia untuk dirangkum.</span>
            </li>
          )}
        </ul>
      </article>

      {/* Right: Implikasi bagi Treasury (interaktif, inline expandable pada halaman yang sama) */}
      <TreasuryImplicationsCard report={report} />
    </div>
  );
}

function MarketReferences({ report }: { report: MarketReport }) {
  const bi = report.bi && typeof report.bi === "object" ? report.bi : {};
  const biRate = bi["BI Rate"] ?? report.macro_indicators?.["BI Rate (%)"]?.today ?? 5.75;
  const indonia = bi.INDONIA ?? 5.75;
  const spread = report.spread_sbn10_ust10_bp ?? 200;

  return (
    <section className="monetary-spread-strip" id="references" aria-label="Indikator acuan">
      <div className="strip-col-title">
        <span>MONETARY & SPREAD</span>
      </div>
      <div className="strip-divider" />
      <div className="strip-col-item">
        <span className="strip-label">BI Rate</span>
        <strong className="strip-value">{typeof biRate === "number" ? `${decimalFormat.format(biRate)}%` : "5,75%"}</strong>
      </div>
      <div className="strip-divider" />
      <div className="strip-col-item">
        <span className="strip-label">INDONIA</span>
        <strong className="strip-value">{typeof indonia === "number" ? `${decimalFormat.format(indonia)}%` : "5,75%"}</strong>
      </div>
      <div className="strip-divider" />
      <div className="strip-col-item">
        <span className="strip-label">Spread SBN – UST 10Y</span>
        <strong className="strip-value">{typeof spread === "number" ? `${numberFormat.format(spread)} bps` : "200 bps"}</strong>
      </div>
    </section>
  );
}

export function Dashboard({ report, histories = {} }: { report: MarketReport; histories?: Record<string, HistoryPoint[]> }) {
  const kpiConfigs: KpiCardConfig[] = [
    { title: "USD/IDR", subtitle: "Rupiah per Dolar AS", section: "fx", fragments: ["USD/IDR"], historyId: "usd-idr" },
    { title: "IHSG", subtitle: "Indeks Harga Saham Gabungan", section: "indices", fragments: ["IHSG"], historyId: "ihsg" },
    { title: "SBN 10Y", subtitle: "Indeks SBN 10 Tahun", section: "yields", fragments: ["ID SBN 10 Tahun", "ID SBN 10Y", "SBN 10"], historyId: "sbn-10y" },
    { title: "UST 10Y", subtitle: "US Treasury 10 Tahun", section: "yields", fragments: ["US Treasury 10 Tahun", "US Treasury 10Y", "UST 10"], historyId: "us-10y" },
    { title: "Emas Antam", subtitle: "Harga Emas Antam", section: "commodities", fragments: ["Emas Antam"], historyId: "antam", isAntam: true },
  ];

  const published = report.published_at || report.generated_at;

  return (
    <div className="workspace">
      {/* Sidebar Navigation */}
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="Market Today beranda">
          <span className="brand-mark">M</span>
          <span className="brand-text">market<span className="brand-light">today</span></span>
        </a>
        <p className="sidebar-label">JELAJAHI PASAR</p>
        <DashboardNav />
        <div className="sidebar-bottom">
          <div className="sidebar-radar">
            <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="#2DD4BF" strokeWidth="1.8" aria-hidden="true">
              <circle cx="12" cy="12" r="10" />
              <circle cx="12" cy="12" r="6" />
              <circle cx="12" cy="12" r="2" fill="#2DD4BF" />
            </svg>
          </div>
          <div className="sidebar-bottom-texts">
            <p>Daily Market Report</p>
            <small>Informasi pasar harian</small>
          </div>
        </div>
      </aside>

      {/* Main Content */}
      <main className="main-content" id="overview">
        <div className="dashboard-container">
          {/* Topbar */}
          <header className="topbar">
            <span className="topbar-kicker">DAILY MARKET INTELLIGENCE</span>
            <div className="topbar-actions">
              <DashboardViewSwitcher active="daily" />
              <StatusPill demo={report.is_demo} />
              <AppearanceControls />
              {!report.is_demo && <OperatorMenu />}
            </div>
          </header>

          {/* Page Intro / Header */}
          <section className="page-intro">
            <div className="intro-main">
              <p className="eyebrow">PASAR KEUANGAN · INDONESIA & GLOBAL</p>
              <h1 className="intro-title">Market <span className="title-teal">Today</span></h1>
              <p className="intro-copy">Ringkasan pasar keuangan Indonesia dan global.</p>
            </div>
            <div className="report-date-box">
              <strong className="report-main-date">{formatReportDate(report)}</strong>
              <span className="report-pub-time">Publikasi {formatPublishedAt(published)}</span>
              <small className="report-obs-note">Menggunakan observasi terbaru setiap instrumen.</small>
            </div>
          </section>

          {/* 5 KPI Cards in ONE ROW */}
          <section className="kpi-row" aria-label="Indikator utama pasar">
            {kpiConfigs.map((cfg) => (
              <KpiCard key={cfg.title} config={cfg} report={report} history={histories[cfg.historyId] ?? []} />
            ))}
          </section>

          {/* Insight Hari Ini & Implikasi bagi Treasury */}
          <ReportInsights report={report} />

          {/* Narasi pasar (teks laporan terbit; tidak tersedia untuk data demo) */}
          {!report.is_demo && <NarrativePanel report={report} />}

          {/* Pergerakan Pasar (Chart Section) */}
          {!report.is_demo && <HistoryCharts histories={histories} />}

          {/* Monetary & Spread Strip */}
          <MarketReferences report={report} />

          {/* Data Pasar (Tables & Tabs) */}
          <MarketDataSections report={report} />

          {/* Unduh Laporan PDF (Bottom Card) */}
          <section className="bottom-export-card" id="export" aria-label="Unduh laporan">
            <div className="export-left">
              <div className="export-icon-box">
                <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8z" />
                  <polyline points="14 2 14 8 20 8" />
                  <line x1="16" y1="13" x2="8" y2="13" />
                  <line x1="16" y1="17" x2="8" y2="17" />
                  <line x1="10" y1="9" x2="8" y2="9" />
                </svg>
              </div>
              <div className="export-text">
                <p className="eyebrow">UNDUH LAPORAN</p>
                <h2 className="export-title">Unduh laporan PDF</h2>
                <p className="export-desc">Simpan ringkasan pasar ini untuk dibaca atau dibagikan.</p>
              </div>
            </div>
            <ExportReportButton reportId={report.report_id} />
          </section>

          {/* Bottom Disclaimer */}
          <footer className="dashboard-bottom-disclaimer">
            <span>*Grafik ilustratif, bukan riwayat pasar aktual.</span>
          </footer>
        </div>
      </main>
    </div>
  );
}

export function DashboardUnavailable({ message }: { message: string }) {
  return (
    <main className="unavailable-page">
      <div className="unavailable-card">
        <span className="brand-mark">M</span>
        <p className="eyebrow">MARKET TODAY</p>
        <h1>Laporan belum dapat ditampilkan.</h1>
        <p>{message}</p>
        <ReloadPageButton />
      </div>
    </main>
  );
}
