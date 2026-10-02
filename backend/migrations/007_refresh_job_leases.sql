ALTER TABLE refresh_jobs
    ADD COLUMN IF NOT EXISTS owner_token UUID,
    ADD COLUMN IF NOT EXISTS lease_until TIMESTAMPTZ;

CREATE INDEX IF NOT EXISTS refresh_jobs_lease_idx
    ON refresh_jobs (lease_until)
    WHERE status = 'running';

-- Job lama tanpa lease dapat dipulihkan oleh worker setelah migrasi.
UPDATE refresh_jobs
SET lease_until = now()
WHERE status = 'running' AND lease_until IS NULL;
