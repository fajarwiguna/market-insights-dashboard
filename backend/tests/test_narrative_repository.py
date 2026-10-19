"""Uji audit trail narasi di PostgreSQL (migrasi 017).

Dilewati bila DATABASE_URL tidak tersedia. Data uji dihapus kembali di akhir.
"""

from __future__ import annotations

import os

import pytest

from market_report.config import load_environment
from market_report.infrastructure.repositories.narrative_repository import (
    PostgresNarrativeRepository,
)


def _repository() -> PostgresNarrativeRepository | None:
    load_environment()
    if not os.environ.get("DATABASE_URL", "").strip():
        return None
    try:
        repository = PostgresNarrativeRepository.from_environment()
        with repository._connect() as connection:
            connection.execute("SELECT 1")
        return repository
    except Exception:
        return None


REPOSITORY = _repository()

pytestmark = pytest.mark.skipif(REPOSITORY is None, reason="PostgreSQL belum tersedia untuk uji audit narasi")


def test_migration_tables_exist():
    with REPOSITORY._connect() as connection:
        tables = {row["tablename"] for row in connection.execute(
            "SELECT tablename FROM pg_tables WHERE schemaname = 'public'").fetchall()}
        versions = {row["version"] for row in connection.execute(
            "SELECT version FROM schema_migrations").fetchall()}
    assert {"narrative_runs", "narrative_outputs", "narrative_evidence", "narrative_claims"} <= tables
    assert "017_narratives.sql" in versions


def test_save_and_read_back_run_with_evidence_and_claims():
    run_id = "test" + os.urandom(6).hex()
    record = {"run_id": run_id, "page": "dashboard", "report_id": "report-test",
              "report_date": "2026-10-16", "status": "published", "rules_path": "docs/llm_rules.md",
              "rules_hash": "abc123", "prompt_version": "v1", "provider": "openai-compatible",
              "model": "m", "context_hash": "ctx", "cache_key": "key", "latency_ms": 1234,
              "tokens_in": 100, "tokens_out": 50, "cost_usd": 0.0012, "repair_count": 1,
              "evidence_count": 1, "validation": {"passed": True, "numbers_used": 3}}
    evidence = [{"evidence_id": "E1", "url": "https://bi.go.id/siaran", "source": "bi.go.id",
                 "source_tier": "official_primary", "published_at": "2026-10-15", "relevance": 0.91,
                 "summary": "Bank Indonesia menjaga stabilitas rupiah."}]
    claims = [{"claim_id": "C1", "text": "BI menyatakan komitmen stabilitas.", "claim_type": "statement",
               "evidence_ids": ["E1"], "accepted": True}]
    try:
        assert REPOSITORY.save_run(record, narrative="IHSG menguat 0,5% pada 16 Oktober 2026.",
                                   output={"narrative": "IHSG menguat 0,5%", "page": "dashboard"},
                                   published=True, evidence=evidence, claims=claims) is True

        detail = REPOSITORY.get_run(run_id)
        assert detail["status"] == "published"
        assert detail["validation"]["passed"] is True
        assert detail["output"]["published"] is True
        assert detail["claims"][0]["accepted"] is True
        assert detail["evidence"][0]["used_in_claims"] is True, (
            "bukti yang dipakai klaim harus ditandai")
        assert float(detail["cost_usd"]) == pytest.approx(0.0012)  # NUMERIC kembali sebagai Decimal

        recent = REPOSITORY.recent_runs(page="dashboard", limit=50)
        assert run_id in {row["run_id"] for row in recent}
    finally:
        with REPOSITORY._connect() as connection:
            connection.execute("DELETE FROM narrative_runs WHERE run_id = %s", (run_id,))


def test_save_run_is_idempotent():
    run_id = "test" + os.urandom(6).hex()
    record = {"run_id": run_id, "page": "equity_snapshot", "report_id": "r", "report_date": "2026-10-16",
              "status": "fallback", "reason": "provider_unavailable", "rules_hash": "h",
              "prompt_version": "v1", "provider": "none", "context_hash": "c"}
    try:
        REPOSITORY.save_run(record)
        REPOSITORY.save_run(record, narrative="narasi kedua", published=False)
        detail = REPOSITORY.get_run(run_id)
        assert detail["reason"] == "provider_unavailable"
        assert detail["output"]["rendered_text"] == "narasi kedua"
        with REPOSITORY._connect() as connection:
            count = connection.execute("SELECT count(*) AS n FROM narrative_runs WHERE run_id = %s",
                                       (run_id,)).fetchone()["n"]
        assert count == 1
    finally:
        with REPOSITORY._connect() as connection:
            connection.execute("DELETE FROM narrative_runs WHERE run_id = %s", (run_id,))


def test_save_run_without_report_date_is_skipped_before_db():
    # Konteks halaman yang tidak tersedia tidak punya tanggal; jangan menulis ke
    # kolom DATE NOT NULL hanya untuk menemui error.
    repository = PostgresNarrativeRepository("postgresql://user:pass@127.0.0.1:1/none")
    assert repository.save_run({"run_id": "r", "page": "equity_snapshot", "report_id": "",
                                "report_date": "", "status": "fallback", "rules_hash": "h",
                                "prompt_version": "v2", "provider": "none",
                                "context_hash": "c"}) is False


def test_missing_run_returns_none():
    assert REPOSITORY.get_run("tidak-ada-run") is None


def test_repository_from_environment_without_url_is_none(monkeypatch):
    # `.env` akan memuat ulang DATABASE_URL, jadi pemuatan environment dimatikan
    # agar kondisi "tanpa database" benar-benar teruji.
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setattr("market_report.config.load_environment", lambda: None)
    assert PostgresNarrativeRepository.from_environment() is None
