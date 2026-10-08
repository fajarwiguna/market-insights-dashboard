"""Entrypoint FastAPI; jalankan dengan uvicorn market_report.api.main:app."""

import logging
import os

from fastapi import FastAPI
from fastapi.responses import JSONResponse

from market_report.config import load_environment
from market_report.infrastructure.repositories.job_repository import PostgresJobRepository
from market_report.api.routers import artifacts, instruments, jobs, market, reports


logger = logging.getLogger(__name__)
app = FastAPI(
    title="Daily Market Report API",
    version="1.0.0",
    description="API baca untuk laporan pasar harian dan versi historisnya.",
)
app.include_router(reports.router, prefix="/api/v1")
app.include_router(instruments.router, prefix="/api/v1")
app.include_router(market.router, prefix="/api/v1")
app.include_router(jobs.router, prefix="/api/v1")
app.include_router(artifacts.router, prefix="/api/v1")


@app.get("/health", tags=["system"], summary="Pemeriksaan proses API")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["system"], summary="Pemeriksaan kesiapan layanan")
def readiness() -> JSONResponse:
    try:
        load_environment()
        result = PostgresJobRepository.from_environment().readiness(
            scheduler_required=bool(os.environ.get("REFRESH_TIMES", "").strip()),
        )
    except Exception:
        logger.exception("Pemeriksaan kesiapan layanan gagal")
        return JSONResponse(
            status_code=503,
            content={"status": "not_ready", "checks": {"database": "unavailable"}},
        )
    return JSONResponse(
        status_code=200 if result["ready"] else 503,
        content={"status": "ready" if result["ready"] else "not_ready", **result},
    )
