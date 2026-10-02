import "server-only";

export function getServerApiConfig() {
  // Next.js loads web/.env and web/.env.local into the server process.
  // Keep this helper read-only so its behavior is identical in dev and build.
  const baseUrl = process.env.DAILY_MARKET_API_URL?.trim().replace(/\/+$/, "") ||
    (process.env.NODE_ENV === "production" ? "" : "http://127.0.0.1:8000/api/v1");
  return {
    baseUrl,
    readToken: process.env.API_READ_TOKEN?.trim() || "",
    operatorToken: process.env.API_OPERATOR_TOKEN?.trim() || "",
  };
}
