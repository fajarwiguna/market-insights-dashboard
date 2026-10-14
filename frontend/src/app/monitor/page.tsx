import { DashboardUnavailable } from "@/features/dashboard/dashboard";
import { MarketMonitorPage } from "@/features/dashboard/market-monitor-page";
import { getInstrumentHistory, getLatestReport } from "@/lib/api/reports";
import type { HistoryPoint } from "@/lib/api/types";

export const dynamic = "force-dynamic";

const HISTORY_INSTRUMENTS = [
  "usd-idr",
  "eur-idr",
  "cny-idr",
  "jpy-idr",
  "dxy",
  "ihsg",
  "dji",
  "us-10y",
  "us-5y",
  "gold",
  "antam",
  "brent",
  "wti",
];

export default async function MonitorPage() {
  const result = await getLatestReport();
  if (result.kind === "unavailable") return <DashboardUnavailable message={result.message} />;

  const reportId = result.report.report_id || "";
  const historiesEntries = await Promise.all(
    HISTORY_INSTRUMENTS.map(async (id) => {
      try {
        const points = await getInstrumentHistory(id, reportId);
        return [id, points] as const;
      } catch {
        return [id, [] as HistoryPoint[]] as const;
      }
    })
  );
  const histories = Object.fromEntries(historiesEntries);

  return <MarketMonitorPage report={result.report} histories={histories} />;
}
