-- 017_narratives.sql
-- Audit trail LLM Narrative Engine (blueprint §17). Menyimpan setiap run narasi
-- beserta angka yang dipakai, bukti, klaim, dan alasan fallback — cukup untuk
-- menjawab "angka apa yang diberikan ke LLM, rule versi mana, dan bukti apa
-- yang dipakai". Prompt/kredensial tidak pernah disimpan di sini.
--
-- `run_id` berupa teks (16 heksadesimal) agar sama dengan yang ditulis ke log
-- dan berkas audit di runtime/narrative/audit/.

CREATE TABLE IF NOT EXISTS narrative_runs (
    run_id          TEXT PRIMARY KEY,
    page            TEXT NOT NULL CHECK (page IN ('dashboard', 'equity_snapshot')),
    report_id       TEXT NOT NULL,
    report_date     DATE NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('published', 'fallback', 'stale', 'unavailable')),
    reason          TEXT,
    rules_path      TEXT,
    rules_hash      TEXT NOT NULL,
    prompt_version  TEXT NOT NULL,
    provider        TEXT NOT NULL,
    model           TEXT,
    context_hash    TEXT NOT NULL,
    cache_key       TEXT,
    latency_ms      INTEGER CHECK (latency_ms IS NULL OR latency_ms >= 0),
    tokens_in       INTEGER NOT NULL DEFAULT 0 CHECK (tokens_in >= 0),
    tokens_out      INTEGER NOT NULL DEFAULT 0 CHECK (tokens_out >= 0),
    cost_usd        NUMERIC(12, 6) NOT NULL DEFAULT 0 CHECK (cost_usd >= 0),
    repair_count    INTEGER NOT NULL DEFAULT 0 CHECK (repair_count >= 0),
    evidence_count  INTEGER NOT NULL DEFAULT 0 CHECK (evidence_count >= 0),
    validation      JSONB NOT NULL DEFAULT '{}'::jsonb,
    dates           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS narrative_runs_page_dates_idx
    ON narrative_runs (page, dates DESC);
CREATE INDEX IF NOT EXISTS narrative_runs_report_idx
    ON narrative_runs (report_id);

CREATE TABLE IF NOT EXISTS narrative_outputs (
    run_id          TEXT PRIMARY KEY REFERENCES narrative_runs(run_id) ON DELETE CASCADE,
    narrative_json  JSONB NOT NULL,
    rendered_text   TEXT NOT NULL,
    published       BOOLEAN NOT NULL DEFAULT FALSE,
    dates           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS narrative_evidence (
    run_id          TEXT NOT NULL REFERENCES narrative_runs(run_id) ON DELETE CASCADE,
    evidence_id     TEXT NOT NULL,
    url             TEXT NOT NULL,
    source          TEXT NOT NULL,
    source_tier     TEXT NOT NULL,
    published_at    DATE,
    relevance       NUMERIC(4, 3),
    used_in_claims  BOOLEAN NOT NULL DEFAULT FALSE,
    snippet         TEXT,
    PRIMARY KEY (run_id, evidence_id)
);

CREATE TABLE IF NOT EXISTS narrative_claims (
    run_id          TEXT NOT NULL REFERENCES narrative_runs(run_id) ON DELETE CASCADE,
    claim_id        TEXT NOT NULL,
    text            TEXT NOT NULL,
    claim_type      TEXT NOT NULL,
    evidence_ids    TEXT[] NOT NULL DEFAULT '{}',
    accepted        BOOLEAN NOT NULL,
    rejected_reason TEXT,
    PRIMARY KEY (run_id, claim_id)
);

CREATE INDEX IF NOT EXISTS narrative_claims_run_accepted_idx
    ON narrative_claims (run_id, accepted);
