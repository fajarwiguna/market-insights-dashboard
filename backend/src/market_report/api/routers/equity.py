"""Read the last immutable yfinance equity snapshot; fetching belongs to workers."""
from fastapi import APIRouter, Depends, HTTPException

from market_report.api.dependencies import require_read_access
from market_report.services.equity_snapshot_service import load_equity_snapshot
from market_report.services.report_service import load_report
from market_report.domain.equity_snapshot import enrich_equity_indicators

router = APIRouter(prefix="/equity", tags=["equity"], dependencies=[Depends(require_read_access)])


@router.get("/latest")
def latest_equity() -> dict:
    cached = load_equity_snapshot()
    report = {}
    try:
        report = load_report() or {}
        published = report.get("equity_snapshot") or {}
    except Exception:
        published = {}
    candidates = [row for row in (cached, published) if row.get("report_id")
                  and row.get("status") in ("partial", "available")]
    if not candidates:
        raise HTTPException(status_code=404, detail="Data equity belum tersedia. Jalankan refresh worker atau modul equity_snapshot_service.")
    snapshot = max(candidates, key=lambda row: (row.get("report_date") or "", row.get("fetched_at") or ""))
    return enrich_equity_indicators(snapshot, report)
