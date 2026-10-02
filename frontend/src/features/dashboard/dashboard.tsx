import type { HistoryPoint, InstrumentReading, MarketReport } from "@/lib/api/types";
import { StatusPill } from "@/components/status-pill";
import { AppearanceControls } from "@/components/appearance-controls";
import { ExportReportButton } from "@/components/export-report-button";
import { HistoryCharts } from "@/features/dashboard/history-charts";
import { LiveMarketMonitor } from "@/features/dashboard/live-market-monitor";
import { RefreshReportControl } from "@/components/refresh-report-control";

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
    <section className="reference-panel" id="references" aria-label="Indikator acuan">
      <div><p className="eyebrow">MONETARY & SPREAD</p><h2>Indikator acuan</h2></div>
      <div className="reference-items">
        {items.map((item) => <div className="reference-item" key={item.label}><span>{item.label}</span><strong>{item.value}</strong></div>)}
      </div>
    </section>
  );
}

const glossary = [
  ["USD/IDR", "Jumlah Rupiah untuk membeli 1 dolar AS. Kenaikan angka berarti Rupiah melemah."],
  ["DXY", "Indeks kekuatan dolar AS terhadap sejumlah mata uang utama dunia."],
  ["Yield", "Imbal hasil tahunan obligasi. Yield naik biasanya berarti harga obligasi turun."],
  ["Spread", "Selisih imbal hasil SBN dan UST pada tenor yang sama."],
  ["BI Rate", "Suku bunga acuan Bank Indonesia yang menjadi salah satu patokan bunga kredit dan deposito."],
  ["INDONIA", "Suku bunga transaksi pinjam-meminjam Rupiah antarbank untuk tenor semalam."],
  ["IHSG", "Indeks yang menggambarkan pergerakan harga saham di Bursa Efek Indonesia."],
  ["Poin basis (bp)", "Satuan perubahan suku bunga. 1 bp = 0,01%; 25 bp = 0,25%."],
  ["SBN", "Surat Berharga Negara, yaitu surat utang yang diterbitkan pemerintah Indonesia."],
  ["UST", "Surat utang pemerintah Amerika Serikat yang sering menjadi acuan pasar global."],
  ["JISDOR", "Kurs referensi dolar AS terhadap Rupiah yang diterbitkan Bank Indonesia."],
];

function ReaderGuide({ report }: { report: MarketReport }) {
  const insights = report.insights ?? [];
  const impacts = report.impacts ?? [];
  const sources = report.sources ?? [];
  const phei = report.phei_meta;

  return (
    <>
      <section className="reader-section" id="insights" aria-labelledby="insights-heading">
        <div className="section-heading"><div><p className="eyebrow">RINGKASAN & ANALISIS</p><h2 id="insights-heading">Insight Hari Ini</h2></div></div>
        <p className="summary-copy">{report.summary || "Data hari ini belum lengkap untuk menyusun ringkasan otomatis."}</p>
        {insights.length ? <div className="insight-grid">{insights.map((item, index) => (
          <article className={`insight-card tone-${item.tone || "flat"}`} key={`${item.title || "insight"}-${index}`}>
            <h3>{item.title || "Sorotan pasar"}</h3><p>{item.text || "—"}</p>
            {item.dampak && <small><strong>Artinya:</strong> {item.dampak}</small>}
          </article>
        ))}</div> : <p className="empty-section">Belum ada sorotan untuk laporan ini.</p>}
      </section>

      <section className="reader-section" id="impacts" aria-labelledby="impacts-heading">
        <div className="section-heading"><div><p className="eyebrow">KONTEKS PEMBACA</p><h2 id="impacts-heading">Apa Artinya untuk Anda</h2></div></div>
        {impacts.length ? <div className="impact-grid">{impacts.map((item, index) => (
          <article className="impact-card" key={`${item.title || "impact"}-${index}`}><h3>{item.title || "Dampak praktis"}</h3><p>{item.text || "—"}</p></article>
        ))}</div> : <p className="empty-section">Dampak praktis belum tersedia untuk laporan ini.</p>}
      </section>

      <section className="reader-section" id="sources" aria-labelledby="sources-heading">
        <div className="section-heading"><div><p className="eyebrow">VERIFIKASI DATA</p><h2 id="sources-heading">Sumber Data & Metode</h2></div><p>Periksa asal angka dan tanggal observasinya.</p></div>
        {sources.length ? <div className="source-list">{sources.map((source, index) => (
          <details className="source-detail" key={`${source.section || "source"}-${index}`}>
            <summary>{source.section || "Sumber data"}{source.items?.length ? <span>{source.items.length} instrumen</span> : null}</summary>
            <div className="source-content">
              {source.primary && <p><strong>Sumber utama:</strong> {source.primary}</p>}
              {source.url && /^https?:\/\//i.test(source.url) && <p><strong>Tautan:</strong> <a href={source.url} target="_blank" rel="noreferrer">{source.url}</a></p>}
              {source.as_of_label && <p><strong>Per tanggal:</strong> {source.as_of_label}</p>}
              {source.page_title && <p><strong>Judul halaman:</strong> {source.page_title}</p>}
              {source.fetched_at && <p><strong>Diambil pada:</strong> {formatPublishedAt(source.fetched_at)}</p>}
              {source.backup && <p><strong>Sumber pembanding:</strong> {source.backup}{source.backup_as_of ? ` (per ${source.backup_as_of})` : ""}</p>}
              {source.note && <p><strong>Catatan:</strong> {source.note}</p>}
              {!!source.items?.length && <ul>{source.items.map((item, itemIndex) => <li key={`${item.field || "field"}-${itemIndex}`}>
                <code>{item.field || "Instrumen"}</code> · {item.source || source.primary || "sumber tidak dicatat"}
                {item.as_of ? ` · per ${item.as_of}` : ""}{item.series ? ` · seri ${item.series}` : ""}{item.ttm ? ` · tenor ${item.ttm} tahun` : ""}
              </li>)}</ul>}
            </div>
          </details>
        ))}</div> : <p className="empty-section">Metadata sumber belum tersedia pada laporan ini.</p>}
        {phei?.as_of_label && <p className="phei-note">Kurva imbal hasil PHEI yang dipakai bertanggal <strong>{phei.as_of_label}</strong>{phei.source_name ? ` · ${phei.source_name}` : ""}{phei.url ? <> · <a href={phei.url} target="_blank" rel="noreferrer">Lihat sumber</a></> : null}</p>}
      </section>

      <section className="reader-section" id="glossary" aria-labelledby="glossary-heading">
        <div className="section-heading"><div><p className="eyebrow">PANDUAN PEMBACA</p><h2 id="glossary-heading">Glosarium & Cara Membaca</h2></div></div>
        <div className="glossary-wrap"><table><thead><tr><th>Istilah</th><th>Arti sederhana</th></tr></thead><tbody>
          {glossary.map(([term, meaning]) => <tr key={term}><th scope="row">{term}</th><td>{meaning}</td></tr>)}
        </tbody></table></div>
        <p className="guide-note"><strong>Cara membaca:</strong> perubahan harian dibandingkan dengan penutupan hari perdagangan sebelumnya. Arti “naik” bergantung pada indikator: kurs USD/IDR naik berarti Rupiah melemah, sedangkan indeks saham naik berarti pasar saham menguat. Tanggal data bisa berbeda antar sumber.</p>
      </section>
    </>
  );
}

export function Dashboard({ report, histories = {} }: { report: MarketReport; histories?: Record<string, HistoryPoint[]> }) {
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
          <a className="nav-link" href="#insights"><span>✳</span> Insight</a>
          <a className="nav-link" href="#impacts"><span>⌁</span> Dampak</a>
          <a className="nav-link" href="#history"><span>⌁</span> Grafik</a>
          {!report.is_demo && <a className="nav-link" href="#live"><span>◉</span> Monitor live</a>}
          <a className="nav-link" href="#references"><span>⌁</span> Indikator acuan</a>
          <a className="nav-link" href="#sources"><span>◎</span> Sumber</a>
          <a className="nav-link" href="#glossary"><span>?</span> Glosarium</a>
        </nav>
        <div className="sidebar-bottom"><span className="sidebar-orb" />
          <p>Daily Market Report</p><small>Informasi pasar harian</small>
        </div>
      </aside>

      <main className="main-content" id="overview">
        <header className="topbar"><span>DAILY MARKET INTELLIGENCE</span><div className="topbar-actions"><StatusPill demo={report.is_demo} /><AppearanceControls /></div></header>
        <section className="page-intro">
          <div><p className="eyebrow">PASAR KEUANGAN · INDONESIA & GLOBAL</p>
            <h1>Market <span>Today</span></h1>
            <p className="intro-copy">Ringkasan pergerakan pasar dalam satu tampilan.</p>
          </div>
          <div className="report-date"><span>TANGGAL LAPORAN</span><strong>{report.report_date || report.report_date_iso || "—"}</strong>
            <small>Dipublikasikan {formatPublishedAt(published)}</small><ExportReportButton reportId={report.report_id} /></div>
        </section>

        <section className="welcome-panel">
          <div className="welcome-copy"><p className="eyebrow">DAILY BRIEFING</p>
            <h2>Gambaran pasar terbaru, tersaji dengan jelas.</h2>
            <p>Mulai dari indikator utama, lalu telusuri data, tanggal observasi, dan sumbernya pada setiap bagian.</p>
          </div>
          <div className="welcome-art" aria-hidden="true"><span className="art-line line-one" /><span className="art-line line-two" /><span className="art-line line-three" /><span className="art-point" /></div>
        </section>

        <ReaderGuide report={report} />

        <section className="metrics-grid" aria-label="Angka utama">
          {featured.map((item) => <MetricCard key={item.title} title={item.title} section={item.section} metric={findMetric(report, item.section, item.fragments)} />)}
        </section>

        <MarketReferences report={report} />
        {!report.is_demo && <HistoryCharts histories={histories} />}
        {!report.is_demo && <LiveMarketMonitor report={report} />}
        {!report.is_demo && <RefreshReportControl />}
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
