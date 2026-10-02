CREATE TABLE IF NOT EXISTS refresh_jobs (
    job_id UUID PRIMARY KEY,
    job_type TEXT NOT NULL CHECK (job_type = 'refresh'),
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    attempts INTEGER NOT NULL DEFAULT 0 CHECK (attempts >= 0),
    max_attempts INTEGER NOT NULL DEFAULT 3 CHECK (max_attempts > 0),
    dates TIMESTAMPTZ NOT NULL DEFAULT now(),
    report_id TEXT REFERENCES report_versions(report_id),
    error_code TEXT
);

CREATE UNIQUE INDEX IF NOT EXISTS refresh_jobs_single_active_idx
    ON refresh_jobs (job_type) WHERE status IN ('queued', 'running');
CREATE INDEX IF NOT EXISTS refresh_jobs_queue_idx
    ON refresh_jobs (dates) WHERE status = 'queued';

CREATE TABLE IF NOT EXISTS refresh_job_events (
    event_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    job_id UUID NOT NULL REFERENCES refresh_jobs(job_id) ON DELETE CASCADE,
    status TEXT NOT NULL CHECK (status IN ('queued', 'running', 'succeeded', 'failed')),
    dates TIMESTAMPTZ NOT NULL DEFAULT now(),
    details JSONB NOT NULL DEFAULT '{}'::jsonb
);

CREATE INDEX IF NOT EXISTS refresh_job_events_job_dates_idx
    ON refresh_job_events (job_id, dates);
