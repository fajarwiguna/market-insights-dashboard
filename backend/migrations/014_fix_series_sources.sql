-- 014_fix_series_sources.sql
-- Nama tabel dari 013 memakai komponen sumber `bbg` yang keliru: pipeline tidak
-- pernah mengambil data dari Bloomberg. Sumber sebenarnya adalah Yahoo
-- (yfinance / chart API), IDX, dan DJPPR, sehingga tabel diganti menjadi:
--
--   glob_FinancialMarket_bbg_d -> glob_FinancialMarket_yahoo_d  (digabung)
--   glob_Monetary_bbg_d        -> glob_Monetary_yahoo_d
--   glob_Commodity_bbg_d       -> glob_Commodity_yahoo_d        (digabung)
--   natl_FinancialMarket_bbg_d -> natl_FinancialMarket_yahoo_d
--   natl_StockFlow_bbg_d       -> natl_StockFlow_idx_d
--   natl_BondFlow_bbg_d        -> natl_BondFlow_djppr_d
--   meta_date_bbg_d            -> meta_date_idx_d
--
-- Tabel pengganti dibuat oleh `sync_catalog()` dari
-- `timeseries_catalog.PIPELINE_SERIES`, yang tetap menjadi acuan penamaan.

DELETE FROM meta_timeseries WHERE table_name IN (
    'glob_FinancialMarket_bbg_d',
    'glob_Monetary_bbg_d',
    'glob_Commodity_bbg_d',
    'natl_FinancialMarket_bbg_d',
    'natl_StockFlow_bbg_d',
    'natl_BondFlow_bbg_d',
    'meta_date_bbg_d'
);

DELETE FROM meta_table WHERE table_name IN (
    'glob_FinancialMarket_bbg_d',
    'glob_Monetary_bbg_d',
    'glob_Commodity_bbg_d',
    'natl_FinancialMarket_bbg_d',
    'natl_StockFlow_bbg_d',
    'natl_BondFlow_bbg_d',
    'meta_date_bbg_d'
);

DROP TABLE IF EXISTS glob_FinancialMarket_bbg_d;
DROP TABLE IF EXISTS glob_Monetary_bbg_d;
DROP TABLE IF EXISTS glob_Commodity_bbg_d;
DROP TABLE IF EXISTS natl_FinancialMarket_bbg_d;
DROP TABLE IF EXISTS natl_StockFlow_bbg_d;
DROP TABLE IF EXISTS natl_BondFlow_bbg_d;
DROP TABLE IF EXISTS meta_date_bbg_d;
