import { NextResponse } from "next/server";
import { getServerApiConfig } from "@/lib/api/server-config";
import { hasOperatorSession, isSameOrigin } from "@/lib/operator-session";

// Regenerate memanggil LLM di sisi backend; beri ruang lebih dari batas route biasa.
export const maxDuration = 120;

const NARRATIVE_PAGES = new Set(["dashboard", "equity_snapshot"]);
type Context = { params: Promise<{ page: string }> };

function rejectUnknownPage(page: string) {
  return NARRATIVE_PAGES.has(page)
    ? null
    : NextResponse.json({ message: "Halaman narasi tidak dikenal." }, { status: 404 });
}

export async function GET(request: Request, context: Context) {
  const { page } = await context.params;
  const invalid = rejectUnknownPage(page);
  if (invalid) return invalid;

  const { baseUrl, readToken } = getServerApiConfig();
  if (!baseUrl || !readToken) return NextResponse.json({ message: "Konfigurasi API baca belum lengkap." }, { status: 503 });

  const reportId = new URL(request.url).searchParams.get("report_id") ?? "";
  const query = new URLSearchParams({ page });
  if (reportId) query.set("report_id", reportId);

  try {
    const response = await fetch(`${baseUrl}/narratives/latest?${query}`, {
      headers: { Authorization: `Bearer ${readToken}` },
      cache: "no-store",
      signal: AbortSignal.timeout(12_000),
    });
    if (!response.ok) return NextResponse.json({ message: "Narasi belum dapat dimuat." }, { status: response.status });
    return NextResponse.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "Layanan narasi tidak dapat dijangkau." }, { status: 502 });
  }
}

export async function POST(request: Request, context: Context) {
  if (!isSameOrigin(request)) return NextResponse.json({ message: "Permintaan lintas situs ditolak." }, { status: 403 });
  if (!hasOperatorSession(request)) return NextResponse.json({ message: "Login operator diperlukan untuk membuat ulang narasi." }, { status: 401 });

  const { page } = await context.params;
  const invalid = rejectUnknownPage(page);
  if (invalid) return invalid;

  const { baseUrl, operatorToken } = getServerApiConfig();
  if (!baseUrl || !operatorToken) return NextResponse.json({ message: "API_OPERATOR_TOKEN belum dikonfigurasi pada server web." }, { status: 503 });

  const params = new URL(request.url).searchParams;
  const reportId = params.get("report_id") ?? "";
  const query = new URLSearchParams({ page, allow_search: params.get("allow_search") === "false" ? "false" : "true" });
  if (reportId) query.set("report_id", reportId);

  try {
    const response = await fetch(`${baseUrl}/narratives/regenerate?${query}`, {
      method: "POST",
      headers: { Authorization: `Bearer ${operatorToken}` },
      cache: "no-store",
      signal: AbortSignal.timeout(115_000),
    });
    if (!response.ok) {
      const retryAfter = response.headers.get("Retry-After");
      const message = response.status === 429
        ? "Regenerate narasi sedang dibatasi. Coba lagi setelah masa tunggu berakhir."
        : response.status === 401
          ? "Sesi operator tidak lagi valid. Masuk kembali melalui menu Pengelolaan."
          : "Narasi belum dapat dibuat ulang.";
      return NextResponse.json({ message }, { status: response.status, headers: retryAfter ? { "Retry-After": retryAfter, "Cache-Control": "no-store" } : { "Cache-Control": "no-store" } });
    }
    return NextResponse.json(await response.json(), { headers: { "Cache-Control": "no-store" } });
  } catch {
    return NextResponse.json({ message: "Layanan narasi tidak dapat dijangkau." }, { status: 502 });
  }
}
