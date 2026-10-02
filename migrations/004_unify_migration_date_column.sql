DO $migration$
BEGIN
    IF EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'schema_migrations' AND column_name = 'applied_at'
    ) AND NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'schema_migrations' AND column_name = 'dates'
    ) THEN
        ALTER TABLE schema_migrations RENAME COLUMN applied_at TO dates;
    END IF;
END
$migration$;
