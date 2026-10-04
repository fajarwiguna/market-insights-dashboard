"""Pengunduhan artefak laporan yang telah dibuat worker."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from market_report.api.dependencies import require_read_access
from market_report.services.artifact_service import pdf_artifact_path
from market_report.infrastructure.repositories.job_repository import PostgresJobRepository


logger = logging.getLogger(__name__)
router = APIRouter(tags=["artifacts"], dependencies=[Depends(require_read_access)])


@router.get("/artifacts/{artifact_id}", summary="Unduh artefak laporan")
def download_artifact(artifact_id: str) -> FileResponse:
    try:
        artifact = PostgresJobRepository.from_environment().get_artifact_by_id(artifact_id)
    except Exception as error:
        logger.exception("Gagal membaca metadata artefak")
        raise HTTPException(status_code=503, detail="Metadata artefak sedang tidak tersedia.") from error
    if artifact is None:
        raise HTTPException(status_code=404, detail="Artefak tidak ditemukan.")

    path = pdf_artifact_path(artifact)
    if path is None:
        raise HTTPException(status_code=404, detail="Berkas artefak tidak tersedia.")
    return FileResponse(path, media_type="application/pdf", filename=artifact["file_name"])
