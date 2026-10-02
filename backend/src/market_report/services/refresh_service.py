"""Pemilihan jalur refresh sesuai backend yang dikonfigurasi."""

import os


def worker_refresh_enabled() -> bool:
    from market_report.config import load_environment

    load_environment()
    return bool(os.environ.get("DATABASE_URL", "").strip())


def request_refresh() -> dict:
    """Antrekan refresh pada PostgreSQL; gunakan pipeline langsung untuk mode JSON lokal."""
    if worker_refresh_enabled():
        from market_report.infrastructure.repositories.job_repository import PostgresJobRepository

        return {"mode": "queued", "job": PostgresJobRepository.from_environment().enqueue_refresh()}

    from market_report.services.report_service import run_live_pipeline

    return {"mode": "completed", "report": run_live_pipeline()}


def get_refresh_job(job_id: str) -> dict | None:
    from market_report.infrastructure.repositories.job_repository import PostgresJobRepository

    return PostgresJobRepository.from_environment().get_job(job_id)
