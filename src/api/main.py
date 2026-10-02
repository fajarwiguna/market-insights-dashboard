"""Entrypoint FastAPI; jalankan dengan uvicorn api.main:app --app-dir src."""

from fastapi import FastAPI

from api.routers import artifacts, instruments, jobs, market, reports


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
