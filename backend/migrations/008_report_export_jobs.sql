ALTER TABLE refresh_jobs
    DROP CONSTRAINT IF EXISTS refresh_jobs_job_type_check;

ALTER TABLE refresh_jobs
    ADD CONSTRAINT refresh_jobs_job_type_check
    CHECK (job_type IN ('refresh', 'export_pdf'));

DROP INDEX IF EXISTS refresh_jobs_single_active_idx;
CREATE UNIQUE INDEX refresh_jobs_single_active_idx
    ON refresh_jobs (job_type, (COALESCE(report_id, '')))
    WHERE status IN ('queued', 'running');

CREATE TABLE IF NOT EXISTS report_artifacts (
    artifact_id UUID PRIMARY KEY,
    report_id TEXT NOT NULL REFERENCES report_versions(report_id),
    artifact_type TEXT NOT NULL CHECK (artifact_type = 'pdf'),
    file_name TEXT NOT NULL,
    storage_key TEXT NOT NULL,
    dates TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (report_id, artifact_type)
);

CREATE INDEX IF NOT EXISTS report_artifacts_report_dates_idx
    ON report_artifacts (report_id, dates DESC);
