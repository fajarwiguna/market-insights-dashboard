-- 013_timeseries_wide.sql
-- Ganti model narrow (ts_series + ts_observation) dengan model panduan_penamaan.md:
--   1. setiap dataset menjadi TABEL fisik wide dengan nama
--      `{cakupan}_{Subjek}_{sumber}_{frekuensi}` dan kolom `dates` sebagai PK
--      plus satu kolom per series;
--   2. katalog dipindah ke `meta_table` (satu baris per tabel) dan
--      `meta_timeseries` (satu baris per series) sesuai panduan §8.
--
-- Kolom `table` pada panduan dinamai `table_name` di sini karena `table`
-- adalah reserved keyword SQL yang harus dikutip di setiap query.
--
-- Tabel fisik per dataset dibuat oleh `sync_catalog()` dari katalog pipeline
-- (`timeseries_catalog.PIPELINE_SERIES`), sehingga katalog tetap menjadi
-- satu-satunya acuan penamaan. Migrasi ini menyiapkan katalog metadatanya.

CREATE TABLE IF NOT EXISTS meta_table (
    id                    TEXT PRIMARY KEY,
    table_name            TEXT NOT NULL UNIQUE,
    table_title           TEXT NOT NULL,
    scope                 TEXT NOT NULL
        CHECK (scope IN ('glob', 'natl', 'prov', 'reg', 'muni', 'meta')),
    source                TEXT NOT NULL,
    frequency             CHAR(1) NOT NULL
        CHECK (frequency IN ('d', 'w', 'm', 'q', 'y')),
    table_type            TEXT NOT NULL,
    organizational_access TEXT NOT NULL DEFAULT 'public'
);

CREATE TABLE IF NOT EXISTS meta_timeseries (
    id          TEXT PRIMARY KEY,
    table_name  TEXT NOT NULL REFERENCES meta_table(table_name) ON UPDATE CASCADE,
    series_name TEXT NOT NULL,
    series_id   TEXT NOT NULL UNIQUE,
    data_type   TEXT NOT NULL,
    description TEXT NOT NULL,
    unit        TEXT,
    source      TEXT NOT NULL,
    tag         TEXT,
    UNIQUE (table_name, series_name)
);

CREATE INDEX IF NOT EXISTS meta_timeseries_table_idx ON meta_timeseries (table_name);
CREATE INDEX IF NOT EXISTS meta_table_scope_idx ON meta_table (scope);

-- Model lama dipensiunkan setelah data dipindah (isinya hanya data uji).
DROP TABLE IF EXISTS ts_observation;
DROP TABLE IF EXISTS ts_series;
