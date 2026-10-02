import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";
import { getServerApiConfig } from "@/lib/api/server-config";

const COOKIE_NAME = "market_operator_session";
const SESSION_HOURS = 8;

function sessionSecret() {
  const secret = process.env.WEB_OPERATOR_SESSION_SECRET;
  return secret && secret.length >= 32 ? secret : null;
}

function sign(payload: string, secret: string) {
  return createHmac("sha256", secret).update(payload).digest("base64url");
}

function constantTimeEqual(left: string, right: string) {
  const leftBytes = Buffer.from(left);
  const rightBytes = Buffer.from(right);
  return leftBytes.length === rightBytes.length && timingSafeEqual(leftBytes, rightBytes);
}

export function operatorLoginConfigured() {
  return Boolean((process.env.WEB_OPERATOR_PASSWORD?.length ?? 0) >= 16 && sessionSecret() && getServerApiConfig().operatorToken);
}

export function operatorPasswordMatches(candidate: string) {
  const expected = process.env.WEB_OPERATOR_PASSWORD;
  return Boolean(expected && constantTimeEqual(candidate, expected));
}

export function createOperatorSession() {
  const secret = sessionSecret();
  if (!secret) throw new Error("WEB_OPERATOR_SESSION_SECRET is not configured");
  const expiresAt = Math.floor(Date.now() / 1000) + SESSION_HOURS * 60 * 60;
  const payload = String(expiresAt);
  return `${payload}.${sign(payload, secret)}`;
}

export function hasOperatorSession(request: Request) {
  const secret = sessionSecret();
  if (!secret || !operatorLoginConfigured()) return false;
  const cookies = request.headers.get("cookie") || "";
  const entry = cookies.split(";").map((item) => item.trim()).find((item) => item.startsWith(`${COOKIE_NAME}=`));
  if (!entry) return false;
  let value = "";
  try { value = decodeURIComponent(entry.slice(COOKIE_NAME.length + 1)); } catch { return false; }
  const [payload, signature, extra] = value.split(".");
  if (!payload || !signature || extra || !/^\d+$/.test(payload)) return false;
  if (Number(payload) <= Math.floor(Date.now() / 1000)) return false;
  return constantTimeEqual(signature, sign(payload, secret));
}

export function operatorCookie(value: string, maxAge = SESSION_HOURS * 60 * 60) {
  const secure = process.env.NODE_ENV === "production" ? "; Secure" : "";
  return `${COOKIE_NAME}=${encodeURIComponent(value)}; Path=/api/; HttpOnly; SameSite=Strict; Max-Age=${maxAge}${secure}`;
}

export function isSameOrigin(request: Request) {
  const origin = request.headers.get("origin");
  return Boolean(origin && origin === new URL(request.url).origin);
}
