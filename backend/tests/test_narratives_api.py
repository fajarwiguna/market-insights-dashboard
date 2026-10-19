"""Uji endpoint narasi tanpa jaringan dan tanpa kredensial.

Engine disuntikkan supaya test tidak bergantung pada laporan di `runtime/`.
"""

from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from market_report.api.routers import narratives
from market_report.domain.narration_contract import NarrativePage, NarrativeRequest
from market_report.domain.narrative_rules import load_rules
from market_report.services.narration.cache import NarrativeCache, UsageLedger
from market_report.services.narration.engine import NarrativeEngine
from market_report.services.narration.providers.fake import FakeLLMProvider, FakeSearchProvider
from market_report.services.narration.providers.none import NullLLMProvider

from test_narration_engine import GOOD_NARRATIVE, good_output, sample_report, sample_snapshot


@pytest.fixture(autouse=True)
def narrative_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATIVE_DIR", str(tmp_path / "runtime-narrative"))
    monkeypatch.setenv("LLM_NARRATIVE_ENABLED", "false")
    narratives.narrative_regenerations._requests.clear()
    yield
    narratives.narrative_regenerations._requests.clear()


def injected_engine(tmp_path, *, llm=None) -> NarrativeEngine:
    return NarrativeEngine(
        rules=load_rules(), llm=llm or NullLLMProvider("belum dikonfigurasi"),
        search=FakeSearchProvider(), cache=NarrativeCache(tmp_path / "cache"),
        ledger=UsageLedger(tmp_path / "usage"), report_loader=lambda: sample_report(),
        equity_loader=lambda: sample_snapshot(), sleeper=lambda _seconds: None,
        repository=False,
    )


def test_latest_returns_readable_payload_without_llm(tmp_path, monkeypatch):
    llm = FakeLLMProvider([json.dumps(good_output())])
    engine = injected_engine(tmp_path, llm=llm)
    monkeypatch.setattr(narratives, "_engine", lambda: engine)

    payload = narratives.read_latest_narrative(page="dashboard")
    assert payload["page"] == "dashboard"
    assert payload["status"] == "fallback"
    assert payload["report_date"] == "2026-10-16"
    assert payload["narrative"], "halaman harus tetap punya narasi deterministik"
    assert payload["notes"]
    assert llm.calls == [], "pembacaan halaman tidak boleh memanggil LLM"


def test_latest_serves_published_narrative_from_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_NARRATIVE_ENABLED", "true")
    engine = injected_engine(tmp_path, llm=FakeLLMProvider([json.dumps(good_output())]))
    monkeypatch.setattr(narratives, "_engine", lambda: engine)

    engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    payload = narratives.read_latest_narrative(page="dashboard")
    assert payload["status"] == "published"
    assert payload["narrative"] == GOOD_NARRATIVE
    assert payload["validation"]["passed"] is True


def test_latest_rejects_unknown_page():
    with pytest.raises(HTTPException) as error:
        narratives.read_latest_narrative(page="halaman-lain")
    assert error.value.status_code == 422
    assert "dashboard" in error.value.detail


def test_regenerate_without_credentials_still_returns_payload(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_NARRATIVE_ENABLED", "true")
    engine = injected_engine(tmp_path)
    monkeypatch.setattr(narratives, "_engine", lambda: engine)

    payload = narratives.regenerate_narrative(page="equity_snapshot")
    assert payload["page"] == "equity_snapshot"
    assert payload["status"] == "fallback"
    assert payload["reason"] == "provider_unavailable"


def test_regenerate_is_rate_limited(tmp_path, monkeypatch):
    engine = injected_engine(tmp_path)
    monkeypatch.setattr(narratives, "_engine", lambda: engine)
    limiter = narratives.narrative_regenerations
    original_limit, original_window = limiter.limit, limiter.window_seconds
    limiter.limit, limiter.window_seconds = 1, 600
    limiter._requests.clear()
    try:
        narratives.regenerate_narrative(page="dashboard")
        with pytest.raises(HTTPException) as error:
            narratives.regenerate_narrative(page="dashboard")
        assert error.value.status_code == 429
        assert "Retry-After" in (error.value.headers or {})
    finally:
        limiter.limit, limiter.window_seconds = original_limit, original_window
        limiter._requests.clear()


def test_runs_endpoint_exposes_audit_summary(tmp_path, monkeypatch):
    engine = injected_engine(tmp_path)
    monkeypatch.setattr(narratives, "_engine", lambda: engine)
    narratives.regenerate_narrative(page="dashboard")

    rows = narratives.read_narrative_runs(limit=5)["runs"]
    assert rows, "regenerate seharusnya meninggalkan catatan audit"
    assert rows[0]["page"] == "dashboard"
    assert {"run_id", "status", "reason", "rules_hash", "prompt_version"} <= set(rows[0])
