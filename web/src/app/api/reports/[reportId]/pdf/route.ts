import { NextResponse } from "next/server";
import { getServerApiConfig } from "@/lib/api/server-config";

type Context = { params: Promise<{ reportId: string }> };

export async function GET(_request: Request, context: Context) {
  const { baseUrl, readToken: token } = getServerApiConfig();
  if (!baseUrl || !token) return NextResponse.json({ message: "Konfigurasi API web belum lengkap." }, { status: 503 });

  try {
    const { reportId } = await context.params;
    const response = await fetch(`${baseUrl}/reports/${encodeURIComponent(reportId)}/exports/pdf`, {
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(20_000),
    });
    if (!response.ok) return NextResponse.json({ message: "PDF belum tersedia. Pastikan worker ekspor berjalan." }, { status: response.status });
    const headers = new Headers({ "Content-Type": "application/pdf", "Cache-Control": "no-store" });
    const disposition = response.headers.get("content-disposition");
    if (disposition) headers.set("Content-Disposition", disposition);
    else headers.set("Content-Disposition", `attachment; filename="daily-market-${encodeURIComponent(reportId)}.pdf"`);
    return new Response(await response.arrayBuffer(), { status: 200, headers });
  } catch {
    return NextResponse.json({ message: "Berkas PDF tidak dapat diunduh." }, { status: 502 });
  }
}
