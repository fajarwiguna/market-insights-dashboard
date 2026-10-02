CREATE TABLE IF NOT EXISTS refresh_schedule_runs (
    schedule_name TEXT NOT NULL,
    dates TIMESTAMPTZ NOT NULL,
    job_id UUID NOT NULL REFERENCES refresh_jobs(job_id),
    PRIMARY KEY (schedule_name, dates)
);

CREATE INDEX IF NOT EXISTS refresh_schedule_runs_job_idx
    ON refresh_schedule_runs (job_id);
