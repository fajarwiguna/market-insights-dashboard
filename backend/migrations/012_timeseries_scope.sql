-- 012_timeseries_scope.sql
-- Sahkan cakupan series (`scope`) sebagai schema, bukan sekadar konvensi nama.
--
-- Scope diturunkan dari prefix `dataset_code` bergaya
-- `{scope}_{Grup}_{sumber}_{frekuensi}` (contoh: `natl_FinancialMarket_bbg_d`).
--
--   glob  -> lintas negara / global
--   natl  -> nasional (Indonesia)
--   reg   -> regional
--   prov  -> provinsi
--   muni  -> kota / kabupaten
--   meta  -> metadata (kalender, tanggal)
--   other -> cadangan; katalog pipeline tidak seharusnya memakainya
--
-- Daftar ini harus sama persis dengan `SCOPES` di
-- `market_report/services/timeseries_catalog.py`.

ALTER TABLE ts_series ADD COLUMN IF NOT EXISTS scope TEXT;

UPDATE ts_series SET scope = CASE
    WHEN dataset_code ~ '^glob_' THEN 'glob'
    WHEN dataset_code ~ '^natl_' THEN 'natl'
    WHEN dataset_code ~ '^reg_'  THEN 'reg'
    WHEN dataset_code ~ '^prov_' THEN 'prov'
    WHEN dataset_code ~ '^muni_' THEN 'muni'
    WHEN dataset_code ~ '^meta_' THEN 'meta'
    ELSE 'other'
END
WHERE scope IS NULL OR scope = '' OR scope = 'other';

ALTER TABLE ts_series ALTER COLUMN scope SET DEFAULT 'other';
ALTER TABLE ts_series ALTER COLUMN scope SET NOT NULL;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_constraint WHERE conname = 'ts_series_scope_check'
    ) THEN
        ALTER TABLE ts_series ADD CONSTRAINT ts_series_scope_check
            CHECK (scope IN ('glob', 'natl', 'reg', 'prov', 'muni', 'meta', 'other'));
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS ts_series_scope_idx ON ts_series (scope);
