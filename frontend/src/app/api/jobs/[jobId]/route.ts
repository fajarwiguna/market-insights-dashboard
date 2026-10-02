import { NextResponse } from "next/server";
import { getServerApiConfig } from "@/lib/api/server-config";

type Context = { params: Promise<{ jobId: string }> };

export async function GET(_request: Request, context: Context) {
  const { baseUrl, readToken: token } = getServerApiConfig();
  if (!baseUrl || !token) return NextResponse.json({ message: "Konfigurasi API web belum lengkap." }, { status: 503 });

  try {
    const { jobId } = await context.params;
    const response = await fetch(`${baseUrl}/jobs/${encodeURIComponent(jobId)}`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return NextResponse.json({ message: "Status ekspor tidak tersedia." }, { status: response.status });
    return NextResponse.json(await response.json());
  } catch {
    return NextResponse.json({ message: "Layanan status ekspor tidak dapat dijangkau." }, { status: 502 });
  }
}
