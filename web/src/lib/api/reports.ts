import "server-only";

import type { MarketReport } from "@/lib/api/types";

export type LatestReportResult =
  | { kind: "available"; report: MarketReport }
  | { kind: "unavailable"; message: string };

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
