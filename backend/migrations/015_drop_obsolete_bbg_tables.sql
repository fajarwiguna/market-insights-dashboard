-- 015_drop_obsolete_bbg_tables.sql
-- Perbaikan untuk 014: `DROP TABLE IF EXISTS glob_Commodity_bbg_d` ditulis tanpa
-- kutip, sehingga PostgreSQL melipat identifier ke lowercase
-- (`glob_commodity_bbg_d`) dan tidak menemukan tabel sebenarnya yang memakai
-- PascalCase pada komponen Subjek. DROP-nya jadi "skipping" tanpa efek.
--
-- Nama tabel wajib dikutip bila mengandung huruf besar.

DROP TABLE IF EXISTS "glob_FinancialMarket_bbg_d";
DROP TABLE IF EXISTS "glob_Monetary_bbg_d";
DROP TABLE IF EXISTS "glob_Commodity_bbg_d";
DROP TABLE IF EXISTS "natl_FinancialMarket_bbg_d";
DROP TABLE IF EXISTS "natl_StockFlow_bbg_d";
DROP TABLE IF EXISTS "natl_BondFlow_bbg_d";
DROP TABLE IF EXISTS "meta_date_bbg_d";
