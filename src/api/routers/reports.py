"""Endpoint baca laporan aktif dan versi historis."""

import logging

from fastapi import APIRouter, Depends, HTTPException

from api.dependencies import require_read_access
from api.schemas import ReportResponse
from services import report_service


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_read_access)])


def _read_report(report_id: str | None = None) -> dict:
    try:
        report = report_service.load_report() if report_id is None else report_service.load_report_version(report_id)
    except Exception as error:
        logger.exception("Gagal membaca laporan dari repository")
        raise HTTPException(status_code=503, detail="Layanan laporan sedang tidak tersedia.") from error
    if report is None:
        if report_id is None:
            raise HTTPException(status_code=404, detail="Laporan aktif belum tersedia.")
        raise HTTPException(status_code=404, detail="Versi laporan tidak ditemukan.")
    # Snapshot provider tertanam hanya untuk menjaga konsistensi internal UI.
    return {key: value for key, value in report.items() if not key.startswith("_")}


@router.get("/latest", response_model=ReportResponse, summary="Baca laporan aktif")
def read_latest_report() -> dict:
    return _read_report()


@router.get("/{report_id}", response_model=ReportResponse, summary="Baca versi laporan")
def read_report_version(report_id: str) -> dict:
    return _read_report(report_id)
