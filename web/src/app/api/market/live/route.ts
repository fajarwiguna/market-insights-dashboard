import { NextResponse } from "next/server";
import { getServerApiConfig } from "@/lib/api/server-config";

export async function GET() {
  const { baseUrl, readToken: token } = getServerApiConfig();
  if (!baseUrl || !token) return NextResponse.json({ message: "Konfigurasi API baca belum lengkap." }, { status: 503 });

  try {
    const response = await fetch(`${baseUrl}/market/live`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(12_000),
    });
    if (!response.ok) return NextResponse.json({ message: "Harga live belum dapat dimuat." }, { status: response.status });
    return NextResponse.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "Sumber data live tidak dapat dijangkau." }, { status: 502 });
  }
}
