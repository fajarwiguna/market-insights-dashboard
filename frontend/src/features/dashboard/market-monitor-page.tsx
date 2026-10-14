import type { HistoryPoint, MarketReport } from "@/lib/api/types";
import { AppearanceControls } from "@/components/appearance-controls";
import { OperatorMenu } from "@/components/operator-menu";
import { StatusPill } from "@/components/status-pill";
import { DashboardViewSwitcher } from "@/features/dashboard/dashboard-view-switcher";
import { LiveMarketMonitor } from "@/features/dashboard/live-market-monitor";

export function MarketMonitorPage({
  report,
  histories = {},
}: {
  report: MarketReport;
  histories?: Record<string, HistoryPoint[]>;
}) {
  return (
    <main className="main-content monitor-main">
      <header className="topbar">
        <span>DAILY MARKET INTELLIGENCE</span>
        <div className="topbar-actions">
          <DashboardViewSwitcher active="live" />
          <StatusPill demo={report.is_demo} />
          <AppearanceControls />
          {!report.is_demo && <OperatorMenu />}
        </div>
      </header>

      <LiveMarketMonitor report={report} initialHistories={histories} />

      <footer className="page-footer monitor-footer">
        <span>Market Today · Monitor Pasar</span>
        <span>ID laporan acuan: {report.report_id || "belum tersedia"}</span>
      </footer>
    </main>
  );
}
