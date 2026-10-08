import { NextResponse } from "next/server";
import { getServerApiConfig } from "@/lib/api/server-config";

export async function GET() {
  const { baseUrl, readToken } = getServerApiConfig();
  if (!baseUrl || !readToken) return NextResponse.json({ message: "Konfigurasi API equity belum lengkap." }, { status: 503 });
  try {
    const response = await fetch(`${baseUrl}/equity/latest`, {
      headers: { Authorization: `Bearer ${readToken}` }, cache: "no-store",
      signal: AbortSignal.timeout(12_000),
    });
    if (!response.ok) return NextResponse.json({ message: response.status === 404
      ? "Data equity belum diterbitkan. Jalankan refresh data harian."
      : "Data equity belum dapat dimuat." }, { status: response.status });
    return NextResponse.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "API equity tidak dapat dijangkau." }, { status: 502 });
  }
}
