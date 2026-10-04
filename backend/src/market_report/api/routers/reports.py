"""Endpoint baca laporan aktif dan versi historis."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Response, status
from fastapi.responses import FileResponse

from market_report.api.dependencies import require_read_access
from market_report.api.schemas import ExportReadyResponse, JobResponse, ReportResponse
from market_report.api.rate_limits import export_requests
from market_report.services.artifact_service import pdf_artifact_path
from market_report.domain.market_analysis import build_impacts, build_insights, build_summary
from market_report.services import report_service
from market_report.infrastructure.repositories.job_repository import PostgresJobRepository


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
    public_report = {key: value for key, value in report.items() if not key.startswith("_")}
    # Teks analisis dibuat backend agar dashboard baru dan Streamlit memakai
    # aturan bisnis yang sama. Hilangkan penanda tebal lama; UI mengatur gaya sendiri.
    public_report["summary"] = build_summary(public_report)
    public_report["insights"] = [
        {**item, "text": item.get("text", "").replace("<b>", "").replace("</b>", "")}
        for item in build_insights(public_report)
    ]
    public_report["impacts"] = build_impacts(public_report)
    return public_report


@router.get("/latest", response_model=ReportResponse, summary="Baca laporan aktif")
def read_latest_report() -> dict:
    return _read_report()


@router.get("/{report_id}", response_model=ReportResponse, summary="Baca versi laporan")
def read_report_version(report_id: str) -> dict:
    return _read_report(report_id)


@router.post("/{report_id}/exports", status_code=status.HTTP_202_ACCEPTED,
             response_model=JobResponse | ExportReadyResponse, summary="Gunakan PDF tersedia atau antrekan ekspor")
def request_report_export(report_id: str, response: Response) -> dict:
    try:
        if report_service.load_report_version(report_id) is None:
            raise HTTPException(status_code=404, detail="Versi laporan tidak ditemukan.")
        repository = PostgresJobRepository.from_environment()
        artifact = repository.get_artifact(report_id)
        if pdf_artifact_path(artifact) is not None:
            response.status_code = status.HTTP_200_OK
            return {"status": "ready", "report_id": report_id, "artifact_id": artifact["artifact_id"]}
        retry_after = export_requests.admit()
        if retry_after:
            raise HTTPException(status_code=429, detail="Antrean ekspor sedang dibatasi. Coba lagi sebentar.",
                                headers={"Retry-After": str(retry_after)})
        return repository.enqueue_export(report_id)
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
    path = pdf_artifact_path(artifact)
    if path is None:
        raise HTTPException(status_code=404, detail="Berkas PDF tidak tersedia.")
    return FileResponse(path, media_type="application/pdf", filename=artifact["file_name"])
