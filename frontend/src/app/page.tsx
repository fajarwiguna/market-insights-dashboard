import { Dashboard, DashboardUnavailable } from "@/features/dashboard/dashboard";
import { getInstrumentHistory, getLatestReport } from "@/lib/api/reports";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const result = await getLatestReport();
  if (result.kind === "unavailable") return <DashboardUnavailable message={result.message} />;
  const histories = result.report.is_demo ? {} : Object.fromEntries(await Promise.all(
    ["sbn-10y", "usd-idr", "ihsg"].map(async (id) => [id, await getInstrumentHistory(id)] as const),
  ));
  return <Dashboard report={result.report} histories={histories} />;
}
