CREATE TABLE IF NOT EXISTS runtime_service_heartbeats (
    service_name TEXT NOT NULL CHECK (service_name IN ('worker', 'scheduler')),
    instance_id TEXT NOT NULL,
    dates TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (service_name, instance_id)
);

CREATE INDEX IF NOT EXISTS runtime_service_heartbeats_dates_idx
    ON runtime_service_heartbeats (service_name, dates DESC);
