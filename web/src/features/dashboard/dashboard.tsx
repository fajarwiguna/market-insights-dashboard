import type { InstrumentReading, MarketReport } from "@/lib/api/types";
import { StatusPill } from "@/components/status-pill";

type MarketGroup = {
  key: "fx" | "indices" | "yields" | "commodities";
  title: string;
  label: string;
  description: string;
};

const groups: MarketGroup[] = [
  { key: "fx", title: "Kurs & mata uang", label: "01 / FX", description: "Nilai tukar dan indeks dolar" },
  { key: "indices", title: "Indeks saham", label: "02 / EQUITIES", description: "Pasar saham Indonesia dan global" },
  { key: "yields", title: "Imbal hasil obligasi", label: "03 / RATES", description: "Yield pemerintah dan benchmark" },
  { key: "commodities", title: "Komoditas", label: "04 / COMMODITIES", description: "Harga komoditas yang dipantau" },
];

const numberFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 2 });
const preciseFormat = new Intl.NumberFormat("id-ID", { maximumFractionDigits: 3 });

function formatValue(value: unknown, section: MarketGroup["key"], name: string): string {
  if (typeof value !== "number" || !Number.isFinite(value)) return "—";
  if (section === "yields") return `${numberFormat.format(value)}%`;
  if (/idr/i.test(name) && Math.abs(value) >= 100) return numberFormat.format(value);
  return preciseFormat.format(value);
}

function formatChange(reading: InstrumentReading): string {
  if (typeof reading.change_bp === "number" && Number.isFinite(reading.change_bp)) {
    return `${reading.change_bp > 0 ? "+" : ""}${numberFormat.format(reading.change_bp)} bp`;
  }
  if (typeof reading.change_pct === "number" && Number.isFinite(reading.change_pct)) {
    return `${reading.change_pct > 0 ? "+" : ""}${numberFormat.format(reading.change_pct)}%`;
  }
  return "Belum ada perubahan";
}

function findMetric(report: MarketReport, section: MarketGroup["key"], fragments: string[]): [string, InstrumentReading] | null {
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
  section: MarketGroup["key"];
}) {
  const [name, reading]: [string, InstrumentReading] = metric ?? ["Data belum tersedia", {}];
  return (
    <article className="metric-card">
      <div className="metric-heading"><span>{title}</span><span className="metric-arrow" aria-hidden="true">↗</span></div>
      <p className="metric-name">{name}</p>
      <p className="metric-value">{formatValue(reading.today, section, name)}</p>
      <p className="metric-change">{formatChange(reading)}</p>
      <p className="metric-date">Data sumber · {reading.date || "tanggal tidak tersedia"}</p>
    </article>
  );
}

function DataTable({ group, report }: { group: MarketGroup; report: MarketReport }) {
  const rows = Object.entries(report[group.key] ?? {});
  return (
    <section className="market-section" id={group.key} aria-labelledby={`${group.key}-heading`}>
      <div className="section-heading">
        <div><p className="eyebrow">{group.label}</p><h2 id={`${group.key}-heading`}>{group.title}</h2></div>
        <p>{group.description}</p>
      </div>
      {rows.length ? (
        <div className="table-scroll">
          <table>
            <thead><tr><th>Instrumen</th><th>Terakhir</th><th>Perubahan</th><th>Tanggal data</th><th>Sumber</th></tr></thead>
            <tbody>
              {rows.map(([name, reading]) => (
                <tr key={name}>
                  <th scope="row">{name}</th>
                  <td className="table-value">{formatValue(reading.today, group.key, name)}</td>
                  <td>{formatChange(reading)}</td>
                  <td>{reading.date || "—"}</td>
                  <td className="source-cell">{reading.source || "—"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : <p className="empty-section">Belum ada data untuk bagian ini pada laporan aktif.</p>}
    </section>
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
    <section className="reference-panel" aria-label="Indikator acuan">
      <div><p className="eyebrow">MONETARY & SPREAD</p><h2>Indikator acuan</h2></div>
      <div className="reference-items">
        {items.map((item) => <div className="reference-item" key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}
      </div>
    </section>
  );
}

export function Dashboard({ report }: { report: MarketReport }) {
  const featured = [
    { title: "Rupiah", section: "fx" as const, fragments: ["USD/IDR"] },
    { title: "IHSG", section: "indices" as const, fragments: ["IHSG"] },
    { title: "UST 10Y", section: "yields" as const, fragments: ["US Treasury 10 Tahun", "US Treasury 10Y"] },
    { title: "SBN 10Y", section: "yields" as const, fragments: ["ID SBN 10 Tahun", "ID SBN 10Y"] },
  ];
  const published = report.published_at || report.generated_at;

  return (
    <div className="workspace">
      <aside className="sidebar">
        <a className="brand" href="#overview" aria-label="Market Today beranda">
          <span className="brand-mark">M</span><span>market<span className="brand-light">today</span></span>
        </a>
        <p className="sidebar-label">WORKSPACE</p>
        <nav className="side-nav" aria-label="Navigasi dashboard">
          <a className="nav-link nav-active" href="#overview"><span>◫</span> Ringkasan</a>
          {groups.map((group) => <a className="nav-link" href={`#${group.key}`} key={group.key}><span>◦</span>{group.title}</a>)}
          <a className="nav-link" href="#references"><span>⌁</span> Indikator acuan</a>
        </nav>
        <div className="sidebar-bottom"><span className="sidebar-orb" />
          <p>Daily Market Report</p><small>Informasi pasar harian</small>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar"><span>DAILY MARKET INTELLIGENCE</span><StatusPill demo={report.is_demo} /></header>
        <section className="page-intro">
          <div><p className="eyebrow">PASAR KEUANGAN · INDONESIA & GLOBAL</p>
            <h1>Market <span>Today</span></h1>
            <p className="intro-copy">Ringkasan pergerakan pasar dalam satu tampilan.</p>
          </div>
          <div className="report-date"><span>TANGGAL LAPORAN</span><strong>{report.report_date || report.report_date_iso || "—"}</strong>
            <small>Dipublikasikan {formatPublishedAt(published)}</small></div>
        </section>

        <section className="welcome-panel">
          <div className="welcome-copy"><p className="eyebrow">DAILY BRIEFING</p>
            <h2>Gambaran pasar terbaru, tersaji dengan jelas.</h2>
            <p>Mulai dari indikator utama, lalu telusuri data, tanggal observasi, dan sumbernya pada setiap bagian.</p>
          </div>
          <div className="welcome-art" aria-hidden="true"><span className="art-line line-one" /><span className="art-line line-two" /><span className="art-line line-three" /><span className="art-point" /></div>
        </section>

        <section className="metrics-grid" aria-label="Angka utama">
          {featured.map((item) => <MetricCard key={item.title} title={item.title} section={item.section} metric={findMetric(report, item.section, item.fragments)} />)}
        </section>

        <MarketReferences report={report} />
        <div className="market-sections">
          {groups.map((group) => <DataTable key={group.key} group={group} report={report} />)}
        </div>

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
    <a href="/">Coba muat ulang halaman <span aria-hidden="true">↗</span></a>
  </div></main>;
}
