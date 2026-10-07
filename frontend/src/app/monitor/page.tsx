import { DashboardUnavailable } from "@/features/dashboard/dashboard";
import { MarketMonitorPage } from "@/features/dashboard/market-monitor-page";
import { getLatestReport } from "@/lib/api/reports";

export const dynamic = "force-dynamic";

export default async function MonitorPage() {
  const result = await getLatestReport();
  if (result.kind === "unavailable") return <DashboardUnavailable message={result.message} />;
  return <MarketMonitorPage report={result.report} />;
}
