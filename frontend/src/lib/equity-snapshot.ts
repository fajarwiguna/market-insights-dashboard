export type StockContribution = {
  ticker: string; company: string; sector: string; close: number;
  change_pct: number; contribution_points: number; volume_shares: number | null;
};
export type EquitySnapshot = {
  schema_version: number; report_id: string; report_date: string; fetched_at: string;
  status: string; source: string; methodology: string; sector_methodology: string;
  coverage: { valid_count: number; universe_count: number; ratio: number; residual_points: number | null };
  market_performance: { id: string; label: string; level: number | null; change_pct: number | null; date: string | null }[];
  stocks: StockContribution[]; market_leaders: StockContribution[]; market_laggards: StockContribution[];
  narrative_suggestions: { ticker: string; company: string; sector: string; reason: string; contribution_points: number }[];
  narratives: { id: string; title: string; text: string }[];
  headline: string; ihsg: { last: number; change_pct: number };
  foreign_flow: { net_idr: number | null; net_usd_mn: number | null; date: string | null };
  coal: { mtd_pct: number | null; date: string | null };
  foreign_flow_rows: { country: string; date: string | null; daily: number | null; wtd?: number | null; mtd?: number | null; qtd?: number | null; ytd?: number | null; "12m"?: number | null }[];
};

export function formatValue(value: number | null | undefined, decimals = 2, signed = false, locale = "en-US") {
  if (value == null || !Number.isFinite(value)) return "—";
  const text = Math.abs(value).toLocaleString(locale, { minimumFractionDigits: decimals, maximumFractionDigits: decimals });
  return `${value < 0 ? "−" : signed && value > 0 ? "+" : ""}${text}`;
}

export function formatDate(value: string | null | undefined) {
  if (!value || !/^\d{4}-\d{2}-\d{2}$/.test(value)) return "—";
  return new Date(`${value}T00:00:00Z`).toLocaleDateString("en-GB", { day: "2-digit", month: "short", year: "numeric", timeZone: "UTC" });
}

export function stockRow(stock: StockContribution): string[] {
  return [stock.ticker, stock.company, formatValue(stock.close, 0),
    formatValue(stock.change_pct), formatValue(stock.contribution_points),
    stock.volume_shares == null ? "—" : `${formatValue(stock.volume_shares / 1e6)} Mn`];
}

// Match whole tokens against the actual universe. Inline formatting tags do not
// matter because callers supply textContent rather than HTML.
export function mentionedTickers(text: string, universe: Iterable<string>): Set<string> {
  const known = new Set([...universe].map(ticker => ticker.toUpperCase()));
  const tokens = text.toUpperCase().match(/[A-Z0-9]+(?:\.JK)?/g) || [];
  return new Set(tokens.map(token => token.replace(/\.JK$/, "")).filter(token => known.has(token)));
}

export function isEquitySnapshot(value: unknown): value is EquitySnapshot {
  if (!value || typeof value !== "object") return false;
  const row = value as EquitySnapshot;
  const stockValid = (stock: StockContribution) => stock && typeof stock.ticker === "string"
    && typeof stock.company === "string" && [stock.close, stock.change_pct, stock.contribution_points].every(Number.isFinite);
  return row.schema_version === 1 && typeof row.report_id === "string" && typeof row.report_date === "string"
    && !!row.ihsg && Number.isFinite(row.ihsg.last) && Number.isFinite(row.ihsg.change_pct)
    && !!row.coverage && Number.isFinite(row.coverage.valid_count) && Number.isFinite(row.coverage.universe_count)
    && !!row.foreign_flow && !!row.coal && typeof row.headline === "string"
    && Array.isArray(row.market_performance) && row.market_performance.every(item => typeof item.label === "string")
    && [row.stocks, row.market_leaders, row.market_laggards].every(items => Array.isArray(items) && items.every(stockValid))
    && Array.isArray(row.narratives) && row.narratives.every(item => typeof item.text === "string" && typeof item.title === "string")
    && Array.isArray(row.narrative_suggestions) && Array.isArray(row.foreign_flow_rows);
}
