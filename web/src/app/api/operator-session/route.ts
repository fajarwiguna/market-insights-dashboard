import { NextResponse } from "next/server";
import { createOperatorSession, hasOperatorSession, isSameOrigin, operatorCookie, operatorLoginConfigured, operatorPasswordMatches } from "@/lib/operator-session";

export async function GET(request: Request) {
  return NextResponse.json({ authenticated: hasOperatorSession(request), configured: operatorLoginConfigured() }, { headers: { "Cache-Control": "no-store" } });
}

export async function POST(request: Request) {
  if (!isSameOrigin(request)) return NextResponse.json({ message: "Permintaan lintas situs ditolak." }, { status: 403 });
  if (!operatorLoginConfigured()) return NextResponse.json({ message: "Login operator belum dikonfigurasi pada server web." }, { status: 503 });
  try {
    const payload: unknown = await request.json();
    const password = payload && typeof payload === "object" && "password" in payload && typeof payload.password === "string" ? payload.password : "";
    if (!operatorPasswordMatches(password)) return NextResponse.json({ message: "Kata sandi operator tidak sesuai." }, { status: 401 });
    const response = NextResponse.json({ authenticated: true });
    response.headers.set("Set-Cookie", operatorCookie(createOperatorSession()));
    response.headers.set("Cache-Control", "no-store");
    return response;
  } catch {
    return NextResponse.json({ message: "Permintaan login tidak dapat diproses." }, { status: 400 });
  }
}

export async function DELETE(request: Request) {
  if (!isSameOrigin(request)) return NextResponse.json({ message: "Permintaan lintas situs ditolak." }, { status: 403 });
  const response = NextResponse.json({ authenticated: false });
  response.headers.set("Set-Cookie", operatorCookie("", 0));
  response.headers.set("Cache-Control", "no-store");
  return response;
}
