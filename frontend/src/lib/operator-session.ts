import "server-only";

import { createHmac, timingSafeEqual } from "node:crypto";
import { isIP } from "node:net";
import { getServerApiConfig } from "@/lib/api/server-config";

const COOKIE_NAME = "market_operator_session";
const SESSION_HOURS = 8;
const LOGIN_WINDOW_MS = 15 * 60 * 1000;
const LOGIN_MAX_FAILURES = 5;
const LOGIN_MAX_CLIENTS = 2_000;

type LoginAttemptState = { windowStartedAt: number; failures: number; blockedUntil: number };
type LoginGlobal = typeof globalThis & { marketOperatorLoginAttempts?: Map<string, LoginAttemptState> };
const loginAttempts = ((globalThis as LoginGlobal).marketOperatorLoginAttempts ??=
  new Map<string, LoginAttemptState>());

function clientKey(request: Request) {
  if (process.env.WEB_TRUST_PROXY !== "true") return "direct";
  // Enable only behind a proxy that overwrites this header and prevents direct access.
  const realIp = request.headers.get("x-real-ip")?.trim();
  return realIp && isIP(realIp) ? `ip:${realIp.toLowerCase()}` : "direct";
}

function pruneLoginAttempts(now: number) {
  for (const [key, state] of loginAttempts) {
    if (state.blockedUntil <= now && now - state.windowStartedAt >= LOGIN_WINDOW_MS) {
      loginAttempts.delete(key);
    }
  }
}

function boundedClientKey(request: Request, now: number) {
  pruneLoginAttempts(now);
  const key = clientKey(request);
  return loginAttempts.has(key) || loginAttempts.size < LOGIN_MAX_CLIENTS - 1 ? key : "overflow";
}

export function operatorLoginRetryAfter(request: Request, now = Date.now()) {
  const key = boundedClientKey(request, now);
  const state = loginAttempts.get(key);
  if (!state) return 0;
  if (state.blockedUntil > now) return Math.ceil((state.blockedUntil - now) / 1000);
  if (now - state.windowStartedAt >= LOGIN_WINDOW_MS) loginAttempts.delete(key);
  return 0;
}

export function recordOperatorLoginFailure(request: Request, now = Date.now()) {
  const key = boundedClientKey(request, now);
  const current = loginAttempts.get(key);
  if (current && current.blockedUntil > now) return Math.ceil((current.blockedUntil - now) / 1000);
  const state = !current || now - current.windowStartedAt >= LOGIN_WINDOW_MS
    ? { windowStartedAt: now, failures: 0, blockedUntil: 0 }
    : current;
  state.failures += 1;
  if (state.failures >= LOGIN_MAX_FAILURES) state.blockedUntil = now + LOGIN_WINDOW_MS;
  loginAttempts.set(key, state);
  pruneLoginAttempts(now);
  return operatorLoginRetryAfter(request, now);
}

export function clearOperatorLoginFailures(request: Request) {
  loginAttempts.delete(boundedClientKey(request, Date.now()));
}

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
