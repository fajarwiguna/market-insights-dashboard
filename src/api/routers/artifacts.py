"""Pengunduhan artefak laporan yang telah dibuat worker."""

import logging
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import FileResponse

from api.dependencies import require_read_access
from config import report_artifact_directory
from services.job_repository import PostgresJobRepository


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

    storage_key = artifact["storage_key"]
    if Path(storage_key).name != storage_key:
        raise HTTPException(status_code=404, detail="Artefak tidak ditemukan.")
    root = report_artifact_directory()
    path = (root / storage_key).resolve()
    if path.parent != root or not path.is_file():
        raise HTTPException(status_code=404, detail="Berkas artefak tidak tersedia.")
    return FileResponse(path, media_type="application/pdf", filename=artifact["file_name"])
