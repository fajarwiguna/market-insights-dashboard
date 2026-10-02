-- observation date is the one canonical date field for an SBN history point.
ALTER TABLE sbn_history DROP COLUMN IF EXISTS recorded_at;
