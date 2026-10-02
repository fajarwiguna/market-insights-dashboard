"""Endpoint permintaan refresh dan status job."""

import logging

from fastapi import APIRouter, Depends, HTTPException, status

from market_report.api.dependencies import require_operator_access, require_read_access
from market_report.api.schemas import JobResponse
from market_report.infrastructure.repositories.job_repository import PostgresJobRepository


logger = logging.getLogger(__name__)
router = APIRouter(tags=["jobs"])


@router.post("/refresh-jobs", status_code=status.HTTP_202_ACCEPTED,
             response_model=JobResponse, summary="Antrekan pembaruan laporan")
def enqueue_refresh(_: None = Depends(require_operator_access)) -> dict:
    try:
        return PostgresJobRepository.from_environment().enqueue_refresh()
    except Exception as error:
        logger.exception("Gagal membuat job refresh")
        raise HTTPException(status_code=503, detail="Antrean refresh sedang tidak tersedia.") from error


@router.get("/jobs/{job_id}", response_model=JobResponse, summary="Baca status job")
def read_job(job_id: str, _: None = Depends(require_read_access)) -> dict:
    try:
        job = PostgresJobRepository.from_environment().get_job(job_id)
    except Exception as error:
        logger.exception("Gagal membaca status job")
        raise HTTPException(status_code=503, detail="Status job sedang tidak tersedia.") from error
    if job is None:
        raise HTTPException(status_code=404, detail="Job tidak ditemukan.")
    return job
