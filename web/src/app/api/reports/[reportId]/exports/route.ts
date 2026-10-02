import { NextResponse } from "next/server";

type Context = { params: Promise<{ reportId: string }> };

export async function POST(_request: Request, context: Context) {
  const baseUrl = process.env.DAILY_MARKET_API_URL?.replace(/\/+$/, "");
  const token = process.env.API_READ_TOKEN;
  if (!baseUrl || !token) return NextResponse.json({ message: "Konfigurasi API web belum lengkap." }, { status: 503 });

  try {
    const { reportId } = await context.params;
    const response = await fetch(`${baseUrl}/reports/${encodeURIComponent(reportId)}/exports`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return NextResponse.json({ message: "Permintaan ekspor belum dapat diproses. Periksa layanan API dan worker." }, { status: response.status });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ message: "Layanan ekspor tidak dapat dijangkau." }, { status: 502 });
  }
}
