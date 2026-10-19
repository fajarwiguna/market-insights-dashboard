import { Dashboard, DashboardUnavailable } from "@/features/dashboard/dashboard";
import { getInstrumentHistory, getLatestReport } from "@/lib/api/reports";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const result = await getLatestReport();
  if (result.kind === "unavailable") return <DashboardUnavailable message={result.message} />;
  const reportId = result.report.report_id;
  const historyIds = ["usd-idr", "ihsg", "sbn-10y", "us-10y", "antam"];
  const histories = result.report.is_demo || !reportId ? {} : Object.fromEntries(await Promise.all(
    historyIds.map(async (id) => [id, await getInstrumentHistory(id, reportId)] as const),
  ));
  return <Dashboard report={result.report} histories={histories} />;
}

