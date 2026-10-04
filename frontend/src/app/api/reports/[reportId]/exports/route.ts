import { NextResponse } from "next/server";
import { getServerApiConfig } from "@/lib/api/server-config";
import { isSameOrigin } from "@/lib/operator-session";

type Context = { params: Promise<{ reportId: string }> };

export async function POST(request: Request, context: Context) {
  if (!isSameOrigin(request)) return NextResponse.json({ message: "Permintaan lintas situs ditolak." }, { status: 403 });
  const { baseUrl, readToken: token } = getServerApiConfig();
  if (!baseUrl || !token) return NextResponse.json({ message: "Konfigurasi API web belum lengkap." }, { status: 503 });

  try {
    const { reportId } = await context.params;
    const response = await fetch(`${baseUrl}/reports/${encodeURIComponent(reportId)}/exports`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return NextResponse.json({ message: response.status === 429 ? "Terlalu banyak permintaan ekspor. Coba kembali setelah masa tunggu." : "Permintaan ekspor belum dapat diproses. Periksa layanan API dan worker." }, { status: response.status, headers: response.status === 429 ? { "Retry-After": response.headers.get("Retry-After") || "60" } : {} });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ message: "Layanan ekspor tidak dapat dijangkau." }, { status: 502 });
  }
}
