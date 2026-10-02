CREATE TABLE IF NOT EXISTS sbn_history (
    observation_date DATE PRIMARY KEY,
    close DOUBLE PRECISION NOT NULL,
    recorded_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
