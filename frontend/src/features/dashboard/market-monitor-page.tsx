import type { MarketReport } from "@/lib/api/types";
import { AppearanceControls } from "@/components/appearance-controls";
import { OperatorMenu } from "@/components/operator-menu";
import { StatusPill } from "@/components/status-pill";
import { DashboardViewSwitcher } from "@/features/dashboard/dashboard-view-switcher";
import { formatReportDate } from "@/features/dashboard/report-format";
import { LiveMarketMonitor } from "@/features/dashboard/live-market-monitor";

export function MarketMonitorPage({ report }: { report: MarketReport }) {
  return <main className="main-content monitor-main">
    <header className="topbar">
      <span>DAILY MARKET INTELLIGENCE</span>
      <div className="topbar-actions">
        <DashboardViewSwitcher active="live" />
        <StatusPill demo={report.is_demo} />
        <AppearanceControls />
        {!report.is_demo && <OperatorMenu />}
      </div>
    </header>
    <section className="page-intro monitor-intro">
      <div><p className="eyebrow">PEMANTAUAN INTRADAY</p><h1>Monitor <span>Pasar</span></h1>
        <p className="intro-copy">Pergerakan live diperbarui terpisah dari laporan harian yang telah diterbitkan.</p></div>
      <div className="report-date"><span>TANGGAL LAPORAN TERAKHIR</span><strong>{formatReportDate(report)}</strong>
        <small>Snapshot laporan tidak berubah saat monitor diperbarui.</small></div>
    </section>
    <LiveMarketMonitor report={report} />
    <footer className="page-footer"><span>Market Today · Monitor Pasar</span>
      <span>ID laporan acuan: {report.report_id || "belum tersedia"}</span></footer>
  </main>;
}
