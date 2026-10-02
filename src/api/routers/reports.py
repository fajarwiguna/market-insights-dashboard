"""Endpoint baca laporan aktif dan versi historis."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import FileResponse
from pathlib import Path

from api.dependencies import require_read_access
from api.schemas import JobResponse, ReportResponse
from services import report_service
from services.job_repository import PostgresJobRepository


logger = logging.getLogger(__name__)
router = APIRouter(prefix="/reports", tags=["reports"], dependencies=[Depends(require_read_access)])
_REPORT_DIR = Path(__file__).resolve().parents[3] / "reports"


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


@router.post("/{report_id}/exports", status_code=status.HTTP_202_ACCEPTED,
             response_model=JobResponse, summary="Antrekan PDF untuk versi laporan")
def request_report_export(report_id: str) -> dict:
    try:
        if report_service.load_report_version(report_id) is None:
            raise HTTPException(status_code=404, detail="Versi laporan tidak ditemukan.")
        return PostgresJobRepository.from_environment().enqueue_export(report_id)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Gagal membuat job ekspor laporan")
        raise HTTPException(status_code=503, detail="Antrean ekspor sedang tidak tersedia.") from error


@router.get("/{report_id}/exports/pdf", summary="Unduh PDF versi laporan")
def download_report_pdf(report_id: str) -> FileResponse:
    try:
        artifact = PostgresJobRepository.from_environment().get_artifact(report_id)
    except Exception as error:
        logger.exception("Gagal membaca artefak PDF laporan")
        raise HTTPException(status_code=503, detail="Metadata artefak sedang tidak tersedia.") from error
    if artifact is None:
        raise HTTPException(status_code=404, detail="PDF belum tersedia untuk versi laporan ini.")
    key = artifact["storage_key"]
    root = _REPORT_DIR.resolve()
    path = (root / key).resolve()
    if Path(key).name != key or path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Berkas PDF tidak tersedia.")
    return FileResponse(path, media_type="application/pdf", filename=artifact["file_name"])
