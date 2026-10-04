"""Endpoint riwayat harian instrumen yang tersimpan."""

import logging
from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query

from market_report.api.dependencies import require_read_access
from market_report.api.schemas import InstrumentHistoryResponse
from market_report.services.instrument_history_service import ReportVersionNotFound, instrument_history


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/instruments", tags=["instruments"], dependencies=[Depends(require_read_access)])


@router.get("/{instrument_id}/history", response_model=InstrumentHistoryResponse,
            summary="Baca riwayat harian instrumen")
def read_instrument_history(
    instrument_id: str,
    date_from: date | None = Query(default=None, alias="from"),
    date_to: date | None = Query(default=None, alias="to"),
    report_id: str | None = Query(default=None, min_length=1, max_length=100),
) -> dict:
    if date_from and date_to and date_from > date_to:
        raise HTTPException(status_code=422, detail="Parameter from harus sebelum atau sama dengan to.")
    try:
        points = instrument_history(instrument_id, report_id=report_id)
    except ReportVersionNotFound as error:
        raise HTTPException(status_code=404, detail=str(error)) from error
    except Exception as error:
        logger.exception("Gagal membaca riwayat instrumen %s", instrument_id)
        raise HTTPException(status_code=503, detail="Riwayat instrumen sedang tidak tersedia.") from error
    if points is None:
        raise HTTPException(status_code=404, detail="ID instrumen tidak didukung.")

    if date_from or date_to:
        points = [
            point for point in points
            if (date_from is None or date.fromisoformat(point["dates"]) >= date_from)
            and (date_to is None or date.fromisoformat(point["dates"]) <= date_to)
        ]
    return {"instrument_id": instrument_id.lower(), "report_id": report_id, "points": points}
