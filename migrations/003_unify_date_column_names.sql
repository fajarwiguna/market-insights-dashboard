DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'report_versions' AND column_name = 'published_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'report_versions' AND column_name = 'dates'
    ) THEN
        ALTER TABLE report_versions RENAME COLUMN published_at TO dates;
    END IF;

    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'sbn_history' AND column_name = 'observation_date'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'sbn_history' AND column_name = 'dates'
    ) THEN
        ALTER TABLE sbn_history RENAME COLUMN observation_date TO dates;
    END IF;
END
$migration$;

DROP INDEX IF EXISTS report_versions_published_at_idx;
CREATE INDEX IF NOT EXISTS report_versions_dates_idx ON report_versions (dates DESC);
