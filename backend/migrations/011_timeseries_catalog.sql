-- 011_timeseries_catalog.sql
-- Katalog series time-series dan tabel observasi untuk data pipeline harian.
-- Sumber: meta_timeseries.xlsx + pipeline fetch_data.py.

-- ============================================================================
-- A. Katalog series (dari meta_timeseries.xlsx, hanya yang relevan pipeline)
-- ============================================================================
CREATE TABLE IF NOT EXISTS ts_series (
    series_id    TEXT PRIMARY KEY,
    dataset_code TEXT NOT NULL,
    field_code   TEXT NOT NULL,
    frequency    CHAR(1) NOT NULL CHECK (frequency IN ('d','w','m','q','y')),
    value_type   TEXT NOT NULL,
    description  TEXT NOT NULL,
    unit         TEXT,
    source       TEXT,
    tags         TEXT,
    UNIQUE (dataset_code, field_code)
);

CREATE INDEX IF NOT EXISTS ts_series_dataset_idx ON ts_series (dataset_code);
CREATE INDEX IF NOT EXISTS ts_series_frequency_idx ON ts_series (frequency);

-- ============================================================================
-- B. Observasi nilai per tanggal
-- ============================================================================
CREATE TABLE IF NOT EXISTS ts_observation (
    series_id  TEXT NOT NULL REFERENCES ts_series(series_id),
    dates      DATE NOT NULL,
    value      NUMERIC(19,6) NOT NULL,
    fetched_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (series_id, dates)
);
CREATE INDEX IF NOT EXISTS ts_observation_dates_idx ON ts_observation (dates DESC);
CREATE INDEX IF NOT EXISTS ts_observation_series_dates_idx ON ts_observation (series_id, dates DESC);

-- ============================================================================
-- C. Data equity snapshot
-- ============================================================================
CREATE TABLE IF NOT EXISTS equity_snapshot (
    report_id       TEXT PRIMARY KEY,
    dates           DATE NOT NULL,
    previous_dates  DATE,
    fetched_at      TIMESTAMPTZ NOT NULL,
    status          TEXT NOT NULL CHECK (status IN ('partial','available','unavailable')),
    schema_version  INTEGER NOT NULL DEFAULT 1,
    payload         JSONB NOT NULL
);
CREATE INDEX IF NOT EXISTS equity_snapshot_dates_idx ON equity_snapshot (dates DESC);

CREATE TABLE IF NOT EXISTS equity_stock_bar (
    report_id      TEXT NOT NULL REFERENCES equity_snapshot(report_id),
    symbol         TEXT NOT NULL,
    dates          DATE NOT NULL,
    close          NUMERIC(19,4),
    previous_close NUMERIC(19,4),
    volume_shares  BIGINT,
    PRIMARY KEY (report_id, symbol)
);
CREATE INDEX IF NOT EXISTS equity_stock_bar_symbol_idx ON equity_stock_bar (symbol);
-- ============================================================================
-- D. Katalog series yang ditarik pipeline harian
-- ============================================================================
-- Sumber: Bank Indonesia -> _bi_, Yahoo/Bloomberg meta -> bbg,
--         Trading Economics -> trading_economics, PHEI -> phei,
--         Logam Mulia -> logammulia, IDX -> idx,
--         International equity flow -> intl_flow

INSERT INTO ts_series (series_id, dataset_code, field_code, frequency, value_type, description, unit, source, tags)
VALUES
    -- === Indeks global ===
    ('globFinancialMarketbbgd_dji',       'glob_FinancialMarket_bbg_d', 'dji',            'd', 'DECIMAL(19,4)', 'Dow Jones Industrial Average',                        'index',  'bbg',       'indices'),
    ('globFinancialMarketbbgd_spx',       'glob_FinancialMarket_bbg_d', 'spx',            'd', 'DECIMAL(19,4)', 'S&P 500 Index',                                        'index',  'bbg',       'indices'),
    ('globFinancialMarketbbgd_us5y',      'glob_FinancialMarket_bbg_d', 'us5y',           'd', 'DECIMAL(19,4)', 'US Treasury 5-Year Yield',                             '%',      'bbg',       'yields'),
    ('globFinancialMarketbbgd_us10y',     'glob_FinancialMarket_bbg_d', 'us10y',          'd', 'DECIMAL(19,4)', 'US Treasury 10-Year Yield',                            '%',      'bbg',       'yields'),
    ('globFinancialMarketbbgd_us30y',     'glob_FinancialMarket_bbg_d', 'us30y',          'd', 'DECIMAL(19,4)', 'US Treasury 30-Year Yield',                            '%',      'bbg',       'yields'),
    ('globFinancialMarketbbgd_dxy',       'glob_FinancialMarket_bbg_d', 'dxy',            'd', 'DECIMAL(19,4)', 'US Dollar Index (DXY)',                                'index',  'bbg',       'fx'),
    ('globFinancialMarketbbgd_gold',      'glob_FinancialMarket_bbg_d', 'gold',           'd', 'DECIMAL(19,4)', 'Gold Futures (COMEX GC)',                              'USD/oz', 'bbg',       'commodities'),
    ('globFinancialMarketbbgd_wti',       'glob_FinancialMarket_bbg_d', 'wti',            'd', 'DECIMAL(19,4)', 'WTI Crude Oil Futures (NYMEX CL)',                     'USD/bbl','bbg',       'commodities'),
    ('globFinancialMarketbbgd_brent',     'glob_FinancialMarket_bbg_d', 'brent',          'd', 'DECIMAL(19,4)', 'Brent Crude Oil Futures (ICE BZ)',                     'USD/bbl','bbg',       'commodities'),

    -- === Indeks Indonesia ===
    ('natlFinancialMarketbbgd_idxcomposite',  'natl_FinancialMarket_bbg_d', 'idx_composite',       'd', 'DECIMAL(19,4)', 'Indeks Harga Saham Gabungan (IHSG)',               'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxenergy',     'natl_FinancialMarket_bbg_d', 'idx_energy',          'd', 'DECIMAL(19,4)', 'IDX-IC Sector Energi',                              'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxbasic',      'natl_FinancialMarket_bbg_d', 'idx_basic_materials', 'd', 'DECIMAL(19,4)', 'IDX-IC Sector Bahan Baku',                          'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxindust',     'natl_FinancialMarket_bbg_d', 'idx_industrials',     'd', 'DECIMAL(19,4)', 'IDX-IC Sector Industri',                            'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxcyclic',     'natl_FinancialMarket_bbg_d', 'idx_consumer_cycl',   'd', 'DECIMAL(19,4)', 'IDX-IC Sector Konsumen Siklikal',                   'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxnoncyc',     'natl_FinancialMarket_bbg_d', 'idx_consumer_noncyc', 'd', 'DECIMAL(19,4)', 'IDX-IC Sector Konsumen Non-Siklikal',               'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxhealth',     'natl_FinancialMarket_bbg_d', 'idx_healthcare',      'd', 'DECIMAL(19,4)', 'IDX-IC Sector Kesehatan',                           'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxfinance',    'natl_FinancialMarket_bbg_d', 'idx_financials',      'd', 'DECIMAL(19,4)', 'IDX-IC Sector Keuangan',                            'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxpropert',    'natl_FinancialMarket_bbg_d', 'idx_properties',      'd', 'DECIMAL(19,4)', 'IDX-IC Sector Properti & Real Estate',              'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxtechno',     'natl_FinancialMarket_bbg_d', 'idx_technology',      'd', 'DECIMAL(19,4)', 'IDX-IC Sector Teknologi',                           'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxinfra',      'natl_FinancialMarket_bbg_d', 'idx_infrastructure',  'd', 'DECIMAL(19,4)', 'IDX-IC Sector Infrastruktur',                       'index',  'bbg',       'indonesia_equity'),
    ('natlFinancialMarketbbgd_idxtrans',      'natl_FinancialMarket_bbg_d', 'idx_transport',       'd', 'DECIMAL(19,4)', 'IDX-IC Sector Transportasi dan Logistik',           'index',  'bbg',       'indonesia_equity'),

    -- === FX (CEIC meta + Yahoo) ===
    ('natlFinancialMarketceicd_usdidr',   'natl_FinancialMarket_ceic_d', 'usd_idr',  'd', 'DECIMAL(19,4)', 'USD/IDR Exchange Rate',            'IDR',    'ceic',  'fx'),
    ('natlFinancialMarketceicd_euridr',   'natl_FinancialMarket_ceic_d', 'eur_idr',  'd', 'DECIMAL(19,4)', 'EUR/IDR Exchange Rate',            'IDR',    'ceic',  'fx'),
    ('natlFinancialMarketceicd_cnyidr',   'natl_FinancialMarket_ceic_d', 'cny_idr',  'd', 'DECIMAL(19,4)', 'CNY/IDR Exchange Rate',            'IDR',    'ceic',  'fx'),
    ('natlFinancialMarketceicd_jpyidr',   'natl_FinancialMarket_ceic_d', 'jpy_idr',  'd', 'DECIMAL(19,4)', 'JPY/IDR Exchange Rate',            'IDR',    'ceic',  'fx'),

    -- === Suku bunga / rate Indonesia (Bank Indonesia) ===
    ('_bi_bi_rate',        'bi_indicators', 'bi_rate',        'd', 'DECIMAL(19,4)', 'BI-Rate (Bank Indonesia Policy Rate)',        '%',     '_bi_',    'rates'),
    ('_bi_indonia',        'bi_indicators', 'indonia',        'd', 'DECIMAL(19,4)', 'INDONIA Overnight Interbank Rate',            '%',     '_bi_',    'rates'),
    ('_bi_jisdor',         'bi_indicators', 'jisdor',         'd', 'DECIMAL(19,4)', 'JISDOR (BI Reference Rate)',                  'IDR',   '_bi_',    'fx'),

    -- === Yield SBN (PHEI) ===
    ('phei_sbn_5y',        'phei_sbn_yields', 'sbn_5y',  'd', 'DECIMAL(19,4)', 'SBN 5-Year Yield (PHEI)',                     '%',     'phei',    'sbn'),
    ('phei_sbn_10y',       'phei_sbn_yields', 'sbn_10y', 'd', 'DECIMAL(19,4)', 'SBN 10-Year Yield (PHEI)',                    '%',     'phei',    'sbn'),

    -- === Harga Emas Antam (Logam Mulia) ===
    ('logammulia_antam_sell_1g', 'logammulia_antam', 'sell_1g', 'd', 'DECIMAL(19,4)', 'Harga Jual Emas Batangan ANTAM 1 gram',       'IDR/gram', 'logammulia', 'commodities'),

    -- === Commodities (Trading Economics) ===
    ('trading_economics_gold_spot',       'trading_economics', 'gold_spot',       'd', 'DECIMAL(19,4)', 'Gold Spot (USD/troy oz)',                     'USD/oz',          'trading_economics', 'commodities'),
    ('trading_economics_coal_newcastle',  'trading_economics', 'coal_newcastle',  'd', 'DECIMAL(19,4)', 'Coal Newcastle (USD/ton)',                   'USD/ton',         'trading_economics', 'commodities'),
    ('trading_economics_cpo',             'trading_economics', 'cpo',             'd', 'DECIMAL(19,4)', 'CPO Bursa Malaysia (MYR/ton)',               'MYR/ton',         'trading_economics', 'commodities'),

    -- === Arus ekuitas internasional ===
    ('intl_flow_china',   'intl_equity_flow', 'china',   'm', 'DECIMAL(19,4)', 'China Inbound Portfolio Equity Flow',        'USD mn', 'intl_flow', 'capital_flow'),
    ('intl_flow_japan',   'intl_equity_flow', 'japan',   'm', 'DECIMAL(19,4)', 'Japan Inbound Portfolio Equity Flow',        'USD mn', 'intl_flow', 'capital_flow'),
    ('intl_flow_malaysia','intl_equity_flow', 'malaysia','m', 'DECIMAL(19,4)', 'Malaysia Inbound Portfolio Equity Flow',     'USD mn', 'intl_flow', 'capital_flow'),
    ('intl_flow_us',      'intl_equity_flow', 'us',      'm', 'DECIMAL(19,4)', 'US Inbound Portfolio Equity Flow',           'USD mn', 'intl_flow', 'capital_flow'),

    -- === Kalender hari bursa ===
    ('metadatebbgd_idbusinessdates', 'meta_date_bbg_d', 'id_business_dates', 'd', 'DATE', 'IDX Business Dates Calendar',                'date',   'bbg',    'calendar'),

    -- === Macro indicators (BI PDF) ===
    ('_bi_monetary_operations', 'bi_seki', 'monetary_operations', 'm', 'DECIMAL(19,4)', 'Operasi Moneter (SEKI BI Tabel III.1)', 'Rp triliun', '_bi_', 'macro'),
    ('_bi_foreign_reserves',    'bi_seki', 'foreign_reserves',    'm', 'DECIMAL(19,4)', 'Cadangan Devisa (SEKI BI)',             'USD mn',     '_bi_', 'macro'),

    -- === Capital flow IDX ===
    ('idx_capital_flow',  'idx_capital_flow', 'total',   'd', 'DECIMAL(19,4)', 'IDX Capital Flow (Foreign + Domestic)',  'IDR bn', 'idx', 'capital_flow'),

    -- === US Fed Funds (Trading Economics) ===
    ('trading_economics_fed_funds', 'trading_economics', 'fed_funds_rate', 'd', 'DECIMAL(19,4)', 'US Federal Funds Target Rate',           '%', 'trading_economics', 'rates')
ON CONFLICT (series_id) DO NOTHING;
