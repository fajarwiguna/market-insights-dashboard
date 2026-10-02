CREATE TABLE IF NOT EXISTS report_versions (
    report_id TEXT PRIMARY KEY,
    published_at TIMESTAMPTZ NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1,
    payload JSONB NOT NULL
);

CREATE TABLE IF NOT EXISTS active_report (
    slot TEXT PRIMARY KEY CHECK (slot = 'active'),
    report_id TEXT NOT NULL REFERENCES report_versions(report_id)
);

CREATE INDEX IF NOT EXISTS report_versions_published_at_idx
    ON report_versions (published_at DESC);
