import { Dashboard, DashboardUnavailable } from "@/features/dashboard/dashboard";
import { getLatestReport } from "@/lib/api/reports";

export const dynamic = "force-dynamic";

export default async function HomePage() {
  const result = await getLatestReport();
  if (result.kind === "unavailable") return <DashboardUnavailable message={result.message} />;
  return <Dashboard report={result.report} />;
}
