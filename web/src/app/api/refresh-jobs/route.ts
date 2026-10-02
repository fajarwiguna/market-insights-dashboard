import { NextResponse } from "next/server";
import { hasOperatorSession, isSameOrigin } from "@/lib/operator-session";
import { getServerApiConfig } from "@/lib/api/server-config";

export async function POST(request: Request) {
  if (!isSameOrigin(request)) return NextResponse.json({ message: "Permintaan lintas situs ditolak." }, { status: 403 });
  if (!hasOperatorSession(request)) return NextResponse.json({ message: "Login operator diperlukan untuk meminta refresh." }, { status: 401 });
  const { baseUrl, operatorToken: token } = getServerApiConfig();
  if (!baseUrl || !token) return NextResponse.json({ message: "API_OPERATOR_TOKEN belum dikonfigurasi pada server web." }, { status: 503 });

  try {
    const response = await fetch(`${baseUrl}/refresh-jobs`, {
      method: "POST",
      headers: { Authorization: `Bearer ${token}` },
      cache: "no-store",
      signal: AbortSignal.timeout(8_000),
    });
    if (!response.ok) return NextResponse.json({ message: "Permintaan refresh belum dapat diproses." }, { status: response.status });
    return NextResponse.json(await response.json(), { status: response.status });
  } catch {
    return NextResponse.json({ message: "Antrean refresh tidak dapat dijangkau." }, { status: 502 });
  }
}
