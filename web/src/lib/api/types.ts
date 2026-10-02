export type InstrumentReading = {
  today?: number | null;
  prev?: number | null;
  change_pct?: number | null;
  change_bp?: number | null;
  date?: string | null;
  source?: string | null;
  [key: string]: unknown;
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
  commodities?: Record<string, InstrumentReading>;
  bi?: Record<string, unknown>;
  spread_sbn10_ust10_bp?: number | null;
  [key: string]: unknown;
};
