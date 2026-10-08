import "server-only";

import type { HistoryPoint, MarketReport } from "@/lib/api/types";
import { getServerApiConfig } from "@/lib/api/server-config";

export type LatestReportResult =
  | { kind: "available"; report: MarketReport }
  | { kind: "unavailable"; message: string };

function isRecord(value: unknown): value is Record<string, unknown> {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}

function isMarketReport(value: unknown): value is MarketReport {
  if (!isRecord(value)) return false;
  const sections = [
    "fx", "indices", "index_sectors", "yields", "gold", "commodities",
    "capital_flow", "macro_indicators", "monetary_operations",
  ];
  const hasMarketSection = sections.some((section) => isRecord(value[section]));
  if (!hasMarketSection) return false;

  for (const section of sections) {
    const readings = value[section];
    if (readings === undefined) continue;
    if (!isRecord(readings)) return false;
    for (const reading of Object.values(readings)) {
      if (!isRecord(reading)) return false;
      for (const key of [
        "today", "prev", "change_pct", "change_bp", "dtd_pct", "dtd_bp",
        "wtd_pct", "mtd_pct", "qtd_pct", "ytd_pct", "ytd_bp",
        "rolling_1m_pct",
      ]) {
        const number = reading[key];
        if (number !== undefined && number !== null && (typeof number !== "number" || !Number.isFinite(number))) return false;
      }
      for (const key of ["periods", "observations"]) {
        const series = reading[key];
        if (series !== undefined && (!isRecord(series) || Object.values(series).some((number) =>
          number !== null && (typeof number !== "number" || !Number.isFinite(number))))) return false;
      }
    }
  }

  if (value.insights !== undefined && !Array.isArray(value.insights)) return false;
  if (value.impacts !== undefined && !Array.isArray(value.impacts)) return false;
  if (value.sources !== undefined && !Array.isArray(value.sources)) return false;
  return true;
}

export async function getInstrumentHistory(instrumentId: string, reportId: string): Promise<HistoryPoint[]> {
  const { baseUrl, readToken: token } = getServerApiConfig();
  if (!baseUrl || !token) return [];

  try {
    const response = await fetch(`${baseUrl}/instruments/${encodeURIComponent(instrumentId)}/history?report_id=${encodeURIComponent(reportId)}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return [];
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== "object" || !("points" in payload) || !Array.isArray(payload.points)) return [];
    if (!("report_id" in payload) || payload.report_id !== reportId) return [];
    if (!payload.points.every((point) => isRecord(point) && typeof point.dates === "string" &&
      typeof point.close === "number" && Number.isFinite(point.close))) return [];
    return payload.points as HistoryPoint[];
  } catch {
    return [];
  }
}

export async function getLatestReport(): Promise<LatestReportResult> {
  const { baseUrl, readToken: token } = getServerApiConfig();

  if (!baseUrl || !token) {
    return {
      kind: "unavailable",
      message: "API belum siap. Periksa API_READ_TOKEN dan pastikan FastAPI berjalan di alamat DAILY_MARKET_API_URL.",
    };
  }

  try {
    const response = await fetch(`${baseUrl}/reports/latest`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });

    if (response.status === 404) {
      return { kind: "unavailable", message: "Laporan aktif belum tersedia. Jalankan refresh melalui worker terlebih dahulu." };
    }
    if (!response.ok) {
      return { kind: "unavailable", message: `API laporan merespons status ${response.status}.` };
    }

    const payload: unknown = await response.json();
    if (!isMarketReport(payload)) {
      return { kind: "unavailable", message: "API mengembalikan data laporan yang tidak sesuai format." };
    }
    return { kind: "available", report: payload };
  } catch {
    return { kind: "unavailable", message: "Laporan tidak dapat dimuat. Periksa koneksi web ke API." };
  }
}
