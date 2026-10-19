"""Endpoint narasi: membaca hasil tersimpan, dan regenerate khusus operator.

Pembacaan halaman tidak pernah memanggil LLM. Bila belum ada hasil, yang
dikembalikan adalah narasi deterministik dengan status `fallback`, sehingga
dashboard dan PDF tetap tampil.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query

from market_report.api.dependencies import require_operator_access, require_read_access
from market_report.api.rate_limits import SlidingWindowLimiter
from market_report.domain.narration_contract import NarrativePage, NarrativeRequest
from market_report.services.narration import audit
from market_report.services.narration.engine import NarrativeEngine

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/narratives", tags=["narratives"])

# Regenerate manual dibatasi seperti ekspor: mahal dan sebaiknya jarang.
narrative_regenerations = SlidingWindowLimiter(limit=2, window_seconds=300)


def _engine() -> NarrativeEngine:
    return NarrativeEngine()


def _page(value: str) -> NarrativePage:
    try:
        return NarrativePage.parse(value)
    except ValueError as error:
        raise HTTPException(status_code=422,
                            detail="page harus 'dashboard' atau 'equity_snapshot'.") from error


@router.get("/latest", summary="Baca narasi tersimpan untuk halaman (tanpa memanggil LLM)",
            dependencies=[Depends(require_read_access)])
def read_latest_narrative(page: str = Query("dashboard"), report_id: str = "") -> dict:
    try:
        engine = _engine()
        result = engine.latest(_page(page), report_id)
    except HTTPException:
        raise
    except Exception as error:
        logger.exception("Gagal membaca narasi tersimpan")
        raise HTTPException(status_code=503, detail="Layanan narasi sedang tidak tersedia.") from error
    return result.to_payload()


@router.get("/runs", summary="Riwayat pemakaian narasi terbaru (audit ringkas)",
            dependencies=[Depends(require_read_access)])
def read_narrative_runs(page: str = "", limit: int = Query(20, ge=1, le=100)) -> dict:
    try:
        rows = audit.recent_records(page=page, limit=limit)
    except Exception as error:
        logger.exception("Gagal membaca audit narasi")
        raise HTTPException(status_code=503, detail="Audit narasi sedang tidak tersedia.") from error
    allowed = {"run_id", "page", "report_id", "report_date", "status", "reason", "provider",
               "model", "latency_ms", "tokens_in", "tokens_out", "cost_usd", "evidence_count",
               "repair_count", "created_at", "rules_hash", "prompt_version"}
    return {"runs": [{key: row.get(key) for key in allowed if key in row} for row in rows]}


@router.get("/runs/{run_id}", summary="Detail satu run narasi dari audit trail",
            dependencies=[Depends(require_read_access)])
def read_narrative_run(run_id: str) -> dict:
    from market_report.infrastructure.repositories.narrative_repository import (
        PostgresNarrativeRepository,
    )

    try:
        repository = PostgresNarrativeRepository.from_environment()
        detail = repository.get_run(run_id) if repository else None
    except Exception as error:
        logger.exception("Gagal membaca detail run narasi")
        raise HTTPException(status_code=503, detail="Audit narasi sedang tidak tersedia.") from error
    if not detail:
        raise HTTPException(status_code=404, detail="Run narasi tidak ditemukan pada audit trail.")
    return detail


@router.post("/regenerate", summary="Buat ulang narasi sekarang (operator)",
             dependencies=[Depends(require_operator_access)])
def regenerate_narrative(page: str = Query("dashboard"), report_id: str = "",
                         allow_search: bool = Query(True)) -> dict:
    retry_after = narrative_regenerations.admit()
    if retry_after:
        raise HTTPException(status_code=429, detail="Regenerate narasi sedang dibatasi. Coba lagi sebentar.",
                            headers={"Retry-After": str(retry_after)})
    try:
        engine = _engine()
        result = engine.generate(NarrativeRequest(page=_page(page),
                                                  report_id=report_id or None,
                                                  allow_search=allow_search,
                                                  reason="operator"),
                                 force=True)
    except Exception as error:
        logger.exception("Gagal membuat ulang narasi")
        raise HTTPException(status_code=503, detail="Pembuatan narasi sedang gagal.") from error
    payload = result.to_payload()
    payload["reason"] = result.reason
    return payload
