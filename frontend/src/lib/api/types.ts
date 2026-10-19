export type InstrumentReading = {
  today?: number | null;
  prev?: number | null;
  change_pct?: number | null;
  change_bp?: number | null;
  dtd_pct?: number | null;
  dtd_bp?: number | null;
  wtd_pct?: number | null;
  mtd_pct?: number | null;
  rolling_1m_pct?: number | null;
  qtd_pct?: number | null;
  ytd_pct?: number | null;
  ytd_bp?: number | null;
  date?: string | null;
  prev_date?: string | null;
  unit?: string | null;
  availability?: "available" | "partial" | "unavailable" | string;
  availability_note?: string | null;
  periods?: Record<string, number | null>;
  observations?: Record<string, number | null>;
  source?: string | null;
  [key: string]: unknown;
};

export type HistoryPoint = { dates: string; close: number };

export type LiveQuote = {
  status: "available" | "unavailable" | string;
  last?: number | null;
  prev?: number | null;
  change_pct?: number | null;
  dates?: string | null;
  source?: string | null;
};

export type LiveMarket = {
  fetched_at?: string | null;
  status: "available" | "partial" | "unavailable" | string;
  quotes: Record<string, LiveQuote>;
};

export type MarketReport = {
  report_id?: string | null;
  schema_version?: number;
  report_date?: string | null;
  report_date_iso?: string | null;
  generated_at?: string | null;
  published_at?: string | null;
  is_demo?: boolean;
  fx?: Record<string, InstrumentReading>;
  indices?: Record<string, InstrumentReading>;
  yields?: Record<string, InstrumentReading>;
  index_sectors?: Record<string, InstrumentReading>;
  gold?: Record<string, InstrumentReading>;
  commodities?: Record<string, InstrumentReading>;
  capital_flow?: Record<string, InstrumentReading>;
  macro_indicators?: Record<string, InstrumentReading>;
  monetary_operations?: Record<string, InstrumentReading>;
  bi?: Record<string, unknown>;
  spread_sbn10_ust10_bp?: number | null;
  headline?: string | null;
  summary?: string | null;
  insights?: { title?: string; text?: string; dampak?: string; tone?: string }[];
  impacts?: { title?: string; text?: string }[];
  treasury_implications?: {
    id?: string;
    title?: string;
    badge?: string;
    analysis?: string;
    recommendation?: string;
  }[];
  sources?: {
    section?: string;
    primary?: string;
    url?: string;
    as_of_label?: string;
    page_title?: string;
    fetched_at?: string;
    backup?: string;
    backup_as_of?: string;
    note?: string;
    items?: { field?: string; source?: string; as_of?: string; series?: string; ttm?: number }[];
  }[];
  phei_meta?: { as_of_label?: string; source_name?: string; url?: string };
  narrative_frozen?: boolean;
  narrative_status?: string;
  [key: string]: unknown;
};

export type NarrativeSource = {
  url?: string;
  source?: string;
  title?: string;
  published_at?: string | null;
  evidence_id?: string;
  [key: string]: unknown;
};

export type NarrativePayload = {
  page: string;
  status: "published" | "fallback" | "stale" | "unavailable" | string;
  report_id?: string;
  report_date?: string;
  narrative?: string;
  sections?: { id?: string; title?: string; text?: string }[];
  sources?: NarrativeSource[];
  notes?: string[];
  run_id?: string;
  generated_at?: string;
  frozen?: boolean;
  validation?: { passed?: boolean; errors?: unknown[]; warnings?: unknown[]; numbers_used?: number };
  message?: string;
};
