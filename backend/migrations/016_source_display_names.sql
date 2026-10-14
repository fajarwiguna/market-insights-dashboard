-- 016_source_display_names.sql
-- Panduan §8: kolom `source` pada `meta_table` dan `meta_timeseries` diisi
-- penerbit data ("Bank Indonesia", "Trading Economics", …), bukan kode ringkas.
-- Nama tabel tetap memakai kode satu kata (mis. `bi`, `te`) karena bagian dari
-- identifier, sehingga pemetaan di bawah memisahkan keduanya.
--
-- Daftar ini harus sama dengan `SOURCE_NAMES` di
-- `market_report/services/timeseries_catalog.py`.

UPDATE meta_table SET source = CASE source
    WHEN 'bi'    THEN 'Bank Indonesia'
    WHEN 'te'    THEN 'Trading Economics'
    WHEN 'yahoo' THEN 'Yahoo Finance'
    WHEN 'erapi' THEN 'open.er-api.com'
    WHEN 'antam' THEN 'Antam'
    WHEN 'phei'  THEN 'PHEI'
    WHEN 'idx'   THEN 'IDX'
    WHEN 'djppr' THEN 'DJPPR'
    WHEN 'fred'  THEN 'FRED'
    WHEN 'safe'  THEN 'SAFE'
    WHEN 'moj'   THEN 'MOF Japan'
    WHEN 'bm'    THEN 'Bursa Malaysia'
    ELSE source
END;

UPDATE meta_timeseries SET source = CASE source
    WHEN 'bi'    THEN 'Bank Indonesia'
    WHEN 'te'    THEN 'Trading Economics'
    WHEN 'yahoo' THEN 'Yahoo Finance'
    WHEN 'erapi' THEN 'open.er-api.com'
    WHEN 'antam' THEN 'Antam'
    WHEN 'phei'  THEN 'PHEI'
    WHEN 'idx'   THEN 'IDX'
    WHEN 'djppr' THEN 'DJPPR'
    WHEN 'fred'  THEN 'FRED'
    WHEN 'safe'  THEN 'SAFE'
    WHEN 'moj'   THEN 'MOF Japan'
    WHEN 'bm'    THEN 'Bursa Malaysia'
    ELSE source
END;
