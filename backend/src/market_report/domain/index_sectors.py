"""IDX-IC sector index symbols and the initial history seed."""

IDX_IC_SECTOR_INDEXES = (
    ("IDXENERGY", "IDXENERGY.JK", "Energi", "IDX Sector Energy"),
    ("IDXBASIC", "IDXBASIC.JK", "Bahan Baku", "IDX Sector Basic Materials"),
    ("IDXINDUST", "IDXINDUST.JK", "Industri", "IDX Sector Industrials"),
    ("IDXCYCLIC", "IDXCYCLIC.JK", "Konsumen Siklikal", "IDX Sector Consumer Cyclicals"),
    ("IDXNONCYC", "IDXNONCYC.JK", "Konsumen Non-Siklikal", "IDX Sector Consumer Non-Cyclicals"),
    ("IDXHEALTH", "IDXHEALTH.JK", "Kesehatan", "IDX Sector Healthcare"),
    ("IDXFINANCE", "IDXFINANCE.JK", "Keuangan", "IDX Sector Financials"),
    ("IDXPROPERT", "IDXPROPERT.JK", "Properti", "IDX Sector Properties & Real Estate"),
    ("IDXTECHNO", "IDXTECHNO.JK", "Teknologi", "IDX Sector Technology"),
    ("IDXINFRA", "IDXINFRA.JK", "Infrastruktur", "IDX Sector Infrastructures"),
    ("IDXTRANS", "IDXTRANS.JK", "Transportasi dan Logistik", "IDX Sector Transportation & Logistic"),
)

# Yahoo Finance publishes current IDX-IC quotes but not their chart history.
# This official IDX close seeds YtD in the initial year; subsequent reports carry
# forward daily closes and therefore supply future year-opening baselines.
IDX_SECTOR_INITIAL_HISTORY_YEAR = 2026
IDX_SECTOR_INITIAL_HISTORY = {
    "Energi": {"date": "2025-12-30", "close": 4453.35},
    "Bahan Baku": {"date": "2025-12-30", "close": 2058.13},
    "Industri": {"date": "2025-12-30", "close": 2155.08},
    "Konsumen Siklikal": {"date": "2025-12-30", "close": 1226.36},
    "Konsumen Non-Siklikal": {"date": "2025-12-30", "close": 799.78},
    "Kesehatan": {"date": "2025-12-30", "close": 2064.27},
    "Keuangan": {"date": "2025-12-30", "close": 1550.07},
    "Properti": {"date": "2025-12-30", "close": 1172.94},
    "Teknologi": {"date": "2025-12-30", "close": 9528.78},
    "Infrastruktur": {"date": "2025-12-30", "close": 2671.10},
    "Transportasi dan Logistik": {"date": "2025-12-30", "close": 1966.08},
}
IDX_SECTOR_HISTORY_SOURCE = (
    "https://www.idx.co.id/en/market-data/statistical-reports/digital-statistic/"
    "monthly/stock-price-index/daily-idx-indices?filter="
    "eyJ5ZWFyIjoiMjAyNSIsIm1vbnRoIjoiMTIiLCJxdWFydGVyIjowLCJ0eXBlIjoibW9udGhseSJ9"
)
