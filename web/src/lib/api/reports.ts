import "server-only";

import type { HistoryPoint, MarketReport } from "@/lib/api/types";

export type LatestReportResult =
  | { kind: "available"; report: MarketReport }
  | { kind: "unavailable"; message: string };

export async function getInstrumentHistory(instrumentId: string): Promise<HistoryPoint[]> {
  const baseUrl = process.env.DAILY_MARKET_API_URL?.replace(/\/+$/, "");
  const token = process.env.API_READ_TOKEN;
  if (!baseUrl || !token) return [];

  try {
    const response = await fetch(`${baseUrl}/instruments/${encodeURIComponent(instrumentId)}/history`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return [];
    const payload: unknown = await response.json();
    if (!payload || typeof payload !== "object" || !("points" in payload) || !Array.isArray(payload.points)) return [];
    return payload.points.filter((point): point is HistoryPoint =>
      !!point && typeof point === "object" && "dates" in point && typeof point.dates === "string" &&
      "close" in point && typeof point.close === "number" && Number.isFinite(point.close)
    );
  } catch {
    return [];
  }
}

export async function getLatestReport(): Promise<LatestReportResult> {
  const baseUrl = process.env.DAILY_MARKET_API_URL?.replace(/\/+$/, "");
  const token = process.env.API_READ_TOKEN;

  if (!baseUrl || !token) {
    return {
      kind: "unavailable",
      message: "Konfigurasi API belum lengkap. Atur DAILY_MARKET_API_URL dan API_READ_TOKEN pada server web.",
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
    if (!payload || typeof payload !== "object" || Array.isArray(payload)) {
      return { kind: "unavailable", message: "API mengembalikan struktur laporan yang tidak dikenali." };
    }
    return { kind: "available", report: payload as MarketReport };
  } catch {
    return { kind: "unavailable", message: "Laporan tidak dapat dimuat. Periksa koneksi web ke API." };
  }
}
