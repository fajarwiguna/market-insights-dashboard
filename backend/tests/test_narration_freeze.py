"""Uji pembekuan narasi ke laporan terbit dan penerapannya di halaman equity.

Seluruh pengujian memakai provider palsu dan tanpa jaringan/kredensial, mengikuti
pola `test_narration_engine.py`.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import HTTPException

from market_report.api import dependencies
from market_report.api.routers import equity as equity_router
from market_report.domain.narration_contract import NarrativePage
from market_report.domain.narrative_rules import load_rules
from market_report.services.narration import freeze
from market_report.services.narration.cache import NarrativeCache, UsageLedger
from market_report.services.narration.engine import NarrativeEngine
from market_report.services.narration.providers.fake import FakeSearchProvider
from market_report.services.narration.providers.none import NullLLMProvider

from test_narration_engine import sample_report, sample_snapshot


@pytest.fixture(autouse=True)
def narrative_env(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATIVE_DIR", str(tmp_path / "runtime-narrative"))
    monkeypatch.setenv("LLM_NARRATIVE_ENABLED", "false")
    monkeypatch.delenv("NARRATIVE_FREEZE", raising=False)


def frozen_engine(tmp_path) -> NarrativeEngine:
    return NarrativeEngine(
        rules=load_rules(), llm=NullLLMProvider("belum dikonfigurasi"),
        search=FakeSearchProvider(), cache=NarrativeCache(tmp_path / "cache"),
        ledger=UsageLedger(tmp_path / "usage"), report_loader=lambda: sample_report(),
        equity_loader=lambda: sample_snapshot(), sleeper=lambda _seconds: None,
        repository=False,
    )


# ── attach_narratives ───────────────────────────────────────────

def test_freeze_disabled_leaves_report_untouched(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATIVE_FREEZE", "never")
    report = sample_report()
    assert freeze.attach_narratives(report, engine=frozen_engine(tmp_path)) is report
    assert "narrative" not in report


def test_attach_narratives_freezes_dashboard_and_equity(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATIVE_FREEZE", "always")
    report = sample_report()
    report["equity_snapshot"] = sample_snapshot()
    freeze.attach_narratives(report, engine=frozen_engine(tmp_path))

    block = report["narrative"]
    assert block["dashboard"]["status"] == "fallback"
    assert block["dashboard"]["frozen"] is True
    assert freeze.frozen_narrative(report, "dashboard")
    assert block["equity_snapshot"]["status"] == "fallback"
    assert freeze.frozen_sections(report, NarrativePage.EQUITY_SNAPSHOT)
    # Salinan pada laporan equity ikut dibekukan agar halaman equity membacanya.
    assert report["equity_snapshot"]["narrative_frozen"]["status"] == "fallback"


def test_attach_narratives_never_raises_on_engine_failure(tmp_path, monkeypatch):
    monkeypatch.setenv("NARRATIVE_FREEZE", "always")
    engine = frozen_engine(tmp_path)

    def explode(*_args, **_kwargs):
        raise RuntimeError("engine rusak")

    engine.generate = explode  # type: ignore[assignment]
    report = sample_report()
    assert freeze.attach_narratives(report, engine=engine) is report
    assert "narrative" not in report


# ── helper pembacaan ────────────────────────────────────────────

def test_frozen_helpers_return_empty_without_entry():
    assert freeze.frozen_entry({}, "dashboard") is None
    assert freeze.frozen_narrative({}, "dashboard") == ""
    assert freeze.frozen_sections({}, "dashboard") == []


def test_frozen_entry_rejects_non_freezable_status():
    report = {"narrative": {"dashboard": {"status": "unavailable", "narrative": "x"}}}
    assert freeze.frozen_entry(report, "dashboard") is None


# ── apply_frozen_narrative ──────────────────────────────────────

def test_apply_frozen_narrative_prefers_snapshot_entry():
    payload = {"narratives": [{"id": "lama", "title": "Lama", "text": "deterministik"}],
               "narrative_frozen": {"status": "published",
                                    "sections": [{"id": "flow", "title": "Aliran modal",
                                                  "text": "Narasi beku."}]}}
    result = freeze.apply_frozen_narrative(payload)
    assert result["narratives"] == [{"id": "flow", "title": "Aliran modal",
                                     "text": "Narasi beku."}]
    assert result["narrative_frozen"] is True
    assert result["narrative_status"] == "published"
    assert payload["narratives"][0]["id"] == "lama", "payload asal tidak boleh diubah"


def test_apply_frozen_narrative_falls_back_to_report_block():
    report = {"narrative": {"equity_snapshot": {
        "status": "fallback", "sections": [{"id": "s", "title": "T", "text": "beku"}]}}}
    result = freeze.apply_frozen_narrative({"narratives": []}, report)
    assert result["narratives"] == [{"id": "s", "title": "T", "text": "beku"}]
    assert result["narrative_status"] == "fallback"


def test_apply_frozen_narrative_keeps_deterministic_without_sections():
    payload = {"narratives": [{"id": "d", "title": "Deterministik", "text": "x"}],
               "narrative_frozen": {"status": "fallback", "sections": []}}
    result = freeze.apply_frozen_narrative(payload)
    assert result["narratives"] == payload["narratives"]
    assert result["narrative_frozen"] is False
    assert result["narrative_status"] == "fallback"


def test_apply_frozen_narrative_ignores_unknown_status():
    payload = {"narratives": [{"id": "d", "title": "D", "text": "x"}],
               "narrative_frozen": {"status": "stale",
                                    "sections": [{"id": "s", "title": "T", "text": "y"}]}}
    assert freeze.apply_frozen_narrative(payload) is payload


# ── router equity ───────────────────────────────────────────────

def test_equity_router_returns_frozen_sections(monkeypatch):
    snapshot = sample_snapshot()
    snapshot["narrative_frozen"] = {
        "status": "published",
        "sections": [{"id": "flow", "title": "Aliran modal", "text": "Narasi beku equity."}],
    }
    monkeypatch.setattr(equity_router, "load_equity_snapshot", lambda: snapshot)
    monkeypatch.setattr(equity_router, "load_report", lambda: {"report_id": "report-1"})

    payload = equity_router.latest_equity()
    assert payload["narratives"] == [{"id": "flow", "title": "Aliran modal",
                                      "text": "Narasi beku equity."}]
    assert payload["narrative_frozen"] is True
    assert payload["narrative_status"] == "published"


def test_equity_router_keeps_deterministic_without_freeze(monkeypatch):
    snapshot = sample_snapshot()
    monkeypatch.setattr(equity_router, "load_equity_snapshot", lambda: snapshot)
    monkeypatch.setattr(equity_router, "load_report", lambda: {})

    payload = equity_router.latest_equity()
    assert payload["narratives"], "tanpa pembekuan, narasi deterministik tetap terisi"
    assert "narrative_status" not in payload
    assert "narrative_frozen" not in payload


# ── jalur publish ───────────────────────────────────────────────

def test_publish_snapshot_invokes_attach_narratives(monkeypatch):
    from market_report.services import report_service

    calls: list[dict] = []

    def fake_attach(report: dict) -> dict:
        calls.append(report)
        return report

    class _Repository:
        def publish(self, report: dict) -> dict:
            return report

        def list_versions(self, limit: int = 0) -> list:
            return []

    monkeypatch.setattr("market_report.calculate.build_report_data", lambda _snapshot: {"report_id": "r"})
    monkeypatch.setattr("market_report.calculate.persist_json_data", lambda *_a, **_k: None)
    monkeypatch.setattr("market_report.services.commodity_history_service.enrich_commodity_history",
                        lambda *_a, **_k: None)
    monkeypatch.setattr(report_service, "validate_report", lambda _report: None)
    monkeypatch.setattr(report_service, "_repository", lambda _path=None: _Repository())
    monkeypatch.setattr("market_report.services.narration.freeze.attach_narratives", fake_attach)

    report_service.publish_snapshot({"x": 1}, report_path=Path("dummy.json"))
    assert calls, "setiap jalur publish harus melewati attach_narratives"


# ── keamanan regenerate ─────────────────────────────────────────

def test_operator_access_rejects_missing_credentials(monkeypatch):
    monkeypatch.setenv("API_OPERATOR_TOKEN", "rahasia-operator")
    monkeypatch.setattr("market_report.config.load_environment", lambda: None)
    with pytest.raises(HTTPException) as error:
        dependencies.require_operator_access(None)
    assert error.value.status_code == 401
