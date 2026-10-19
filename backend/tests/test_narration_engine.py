"""Uji end-to-end Narrative Engine dengan provider palsu (tanpa jaringan/kredensial)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from market_report.domain.narration_contract import (
    EvidenceItem,
    NarrativePage,
    NarrativeRequest,
    NarrativeStatus,
)
from market_report.domain.narrative_rules import load_rules
from market_report.services.narration import audit, evidence as evidence_module, providers, validators
from market_report.services.narration import signals as signals_module
from market_report.services.narration.cache import NarrativeCache, UsageLedger, cache_key
from market_report.services.narration.context_builder import build_dashboard_context, build_equity_context
from market_report.services.narration.engine import NarrativeEngine
from market_report.services.narration.errors import ProviderUnavailableError
from market_report.services.narration.prompt_builder import build_user_prompt
from market_report.services.narration.providers.base import RawSearchResult
from market_report.services.narration.providers.fake import FakeLLMProvider, FakeSearchProvider
from market_report.services.narration.providers.none import NullLLMProvider
from market_report.services.narration.providers.openai_compatible import OpenAICompatibleProvider

GOOD_NARRATIVE = (
    "Rupiah ditutup di Rp17.903 per dolar AS pada 16 Oktober 2026, sementara IHSG turun 0,75% "
    "ke level 6.147 pada sesi yang sama. Pasar menunggu arah kebijakan moneter domestik dan "
    "perkembangan pasar global sebelum menentukan posisi berikutnya."
)


def sample_report() -> dict:
    return {
        "report_id": "report-1",
        "report_date_iso": "2026-10-16",
        "fx": {"USD/IDR": {"today": 17903, "prev": 17916, "change_pct": 0.07, "date": "2026-10-16"}},
        "indices": {"IHSG (ID)": {"today": 6147, "prev": 6193, "change_pct": -0.75, "date": "2026-10-16"}},
        "yields": {"ID SBN 10 Tahun": {"today": 6.31, "prev": 6.33, "change_bp": -2.4,
                                       "date": "2026-10-15"}},
        "commodities": {},
        "bi": {},
    }


def sample_snapshot() -> dict:
    return {
        "schema_version": 1, "report_id": "equity-1", "report_date": "2026-10-16",
        "status": "available",
        "coverage": {"valid_count": 800, "universe_count": 850, "ratio": 0.94,
                     "residual_points": -5.0},
        "ihsg": {"last": 6147, "change_pct": -0.75, "prev_date": "2026-10-15"},
        "market_performance": [{"id": "IHSG", "label": "JCI (Indonesia)", "level": 6147,
                                "change_pct": -0.75, "date": "2026-10-16"}],
        "market_leaders": [{"ticker": "BBCA", "change_pct": 1.4, "contribution_points": 12.8,
                            "sector": "Financial Services"}],
        "market_laggards": [{"ticker": "GOTO", "change_pct": -3.1, "contribution_points": -6.4,
                             "sector": "Technology"}],
        "sector_contributions": [{"sector": "Financial Services", "contribution_points": 18.2}],
        "foreign_flow": {"net_usd_mn": -98.4, "net_idr": -1.76e12, "date": "2026-10-16",
                         "source": "BEI"},
        "foreign_flow_rows": [{"country": "Indonesia", "date": "2026-10-16", "daily": -98.4,
                               "mtd": -410.2}],
        "coal": {"mtd_pct": 3.12, "date": "2026-10-16", "price": 118.4},
        "narratives": [{"id": "market", "title": "Pergerakan IHSG",
                        "text": "IHSG turun 0,75% ke level 6.147."}],
    }


def good_output(**overrides) -> dict:
    payload = {
        "schema_version": 1,
        "page": "dashboard",
        "narrative": GOOD_NARRATIVE,
        "claims": [],
        "numbers_used": [
            {"key": "fx.usd_idr.last", "value": 17903},
            {"key": "market.ihsg.change_pct", "value": -0.75},
            {"key": "market.ihsg.last", "value": 6147},
        ],
        "narrative_gaps": [],
    }
    payload.update(overrides)
    return payload


def engine_with(tmp_path, responses, **kwargs) -> NarrativeEngine:
    llm = kwargs.pop("llm", FakeLLMProvider(responses))
    return NarrativeEngine(
        rules=kwargs.pop("rules", load_rules()),
        llm=llm,
        search=kwargs.pop("search", FakeSearchProvider()),
        cache=NarrativeCache(tmp_path / "cache"),
        ledger=UsageLedger(tmp_path / "usage"),
        report_loader=lambda: sample_report(),
        equity_loader=lambda: {},
        sleeper=lambda _seconds: None,
        repository=False,  # pengujian tidak boleh menulis ke PostgreSQL
        **kwargs,
    )


@pytest.fixture(autouse=True)
def narrative_env(tmp_path, monkeypatch):
    """Arahkan seluruh berkas runtime narasi ke folder sementara."""
    monkeypatch.setenv("NARRATIVE_DIR", str(tmp_path / "runtime-narrative"))
    monkeypatch.setenv("LLM_NARRATIVE_ENABLED", "true")
    monkeypatch.delenv("LLM_PROVIDER", raising=False)


# ── kontrak keluaran ────────────────────────────────────────────

def test_parse_output_accepts_fenced_json_and_rejects_garbage():
    assert validators.parse_narrative_output('```json\n{"a": 1}\n```')["a"] == 1
    assert validators.parse_narrative_output('teks {"a": 1} selesai')["a"] == 1
    with pytest.raises(Exception):
        validators.parse_narrative_output("bukan json sama sekali")


# ── provider ────────────────────────────────────────────────────

def test_openai_compatible_requires_complete_configuration():
    assert OpenAICompatibleProvider(base_url="", api_key="", model="").available() is False
    assert OpenAICompatibleProvider(base_url="https://x", api_key="k", model="").available() is False
    assert OpenAICompatibleProvider(base_url="https://x", api_key="k", model="m").available() is True


def test_openai_compatible_endpoint_normalisation():
    assert OpenAICompatibleProvider(base_url="https://opus.abhibots.com", api_key="k",
                                    model="m").endpoint() == "https://opus.abhibots.com/v1/chat/completions"
    assert OpenAICompatibleProvider(base_url="https://gw.local/v1", api_key="k",
                                    model="m").endpoint() == "https://gw.local/v1/chat/completions"


class _StubResponse:
    def __init__(self, status_code: int, payload: dict | None = None, text: str = "",
                 headers: dict | None = None):
        self.status_code = status_code
        self._payload = payload or {}
        self.text = text
        self.headers = headers or {}

    def json(self):
        return self._payload


def test_openai_compatible_generate_reads_content_and_usage():
    def post(url, payload, headers, timeout):
        assert url.endswith("/v1/chat/completions")
        assert headers["Authorization"] == "Bearer secret"
        assert payload["response_format"] == {"type": "json_object"}
        return _StubResponse(200, {"model": "m", "choices": [{"message": {"content": "{\"ok\":1}"}}],
                                   "usage": {"prompt_tokens": 12, "completion_tokens": 7}})

    provider = OpenAICompatibleProvider(base_url="https://x", api_key="secret", model="m", post=post)
    response = provider.generate(system="s", user="u")
    assert (response.text, response.tokens_in, response.tokens_out, response.model) == ("{\"ok\":1}", 12, 7, "m")


def test_openai_compatible_retries_without_json_mode_and_maps_errors():
    calls: list[dict] = []

    def post(url, payload, headers, timeout):
        calls.append(payload)
        if "response_format" in payload:
            return _StubResponse(400, text="response_format is not supported")
        return _StubResponse(200, {"choices": [{"message": {"content": "{}"}}], "usage": {}})

    provider = OpenAICompatibleProvider(base_url="https://x", api_key="k", model="m", post=post)
    assert provider.generate(system="s", user="u").text == "{}"
    assert len(calls) == 2 and "response_format" not in calls[1]

    def server_error(url, payload, headers, timeout):
        return _StubResponse(503)

    with pytest.raises(ProviderUnavailableError):
        OpenAICompatibleProvider(base_url="https://x", api_key="k", model="m",
                                 post=server_error).generate(system="s", user="u")


def test_openai_compatible_surfaces_provider_error_and_retry_after():
    def post(url, payload, headers, timeout):
        return _StubResponse(429, {"error": {"type": "rate_limit_error",
                                             "message": "Daily token limit exceeded."}},
                             headers={"Retry-After": "42401"})

    provider = OpenAICompatibleProvider(base_url="https://x", api_key="k", model="m", post=post)
    with pytest.raises(ProviderUnavailableError) as caught:
        provider.generate(system="s", user="u")
    assert "Daily token limit exceeded" in str(caught.value)
    assert caught.value.retry_after == 42401.0


def test_openai_compatible_treats_forbidden_as_provider_failure():
    def post(url, payload, headers, timeout):
        return _StubResponse(403, {"error": {"type": "access_denied",
                                             "message": "You have no permission to access this resource"}})

    provider = OpenAICompatibleProvider(base_url="https://x", api_key="k", model="m", post=post)
    with pytest.raises(ProviderUnavailableError) as caught:
        provider.generate(system="s", user="u")
    assert "no permission" in str(caught.value)


def test_provider_selection_defaults_to_fallback_without_credentials(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "openai-compatible")
    # Dikosongkan (bukan dihapus): load_dotenv(override=False) tidak menimpa
    # variabel yang sudah ada, sehingga .env pengembang tidak bocor ke test ini.
    monkeypatch.setenv("LLM_BASE_URL", "")
    monkeypatch.setenv("LLM_API_KEY", "")
    monkeypatch.setenv("LLM_MODEL", "")
    assert providers.llm_provider().available() is False
    monkeypatch.setenv("LLM_PROVIDER", "none")
    assert isinstance(providers.llm_provider(), NullLLMProvider)


# ── prompt: bagian equity & aturan klaim ────────────────────────

def _equity_context():
    snapshot = sample_snapshot()
    snapshot["narratives"] = [
        {"id": "market", "title": "Pergerakan IHSG dan sikap Investor", "text": "IHSG turun 0,75%."},
        {"id": "macro", "title": "Inflasi dan penyesuaian indeks", "text": "Inflasi stabil."},
        {"id": "foreign", "title": "Arus dana asing", "text": "Asing mencatat outflow."},
        {"id": "sector", "title": "Pergerakan sektoral", "text": "Sektor melemah."},
    ]
    return build_equity_context(snapshot, sample_report())


def test_equity_prompt_requests_sections_matching_page_titles():
    prompt = build_user_prompt(_equity_context(), rules=load_rules())
    assert "<sections>" in prompt
    for title in ("Pergerakan IHSG dan sikap Investor", "Inflasi dan penyesuaian indeks",
                  "Arus dana asing", "Pergerakan sektoral"):
        assert title in prompt, title


def test_dashboard_prompt_has_no_sections_block():
    prompt = build_user_prompt(build_dashboard_context(sample_report()), rules=load_rules())
    assert "<sections>" not in prompt


def test_prompt_forbids_claims_when_no_evidence():
    prompt = build_user_prompt(build_dashboard_context(sample_report()), rules=load_rules(), evidence=[])
    assert "claims` WAJIB array kosong" in prompt


def test_prompt_restricts_claims_to_listed_evidence():
    item = EvidenceItem(evidence_id="ev-1", title="BOJ menahan suku bunga",
                        url="https://reuters.com/a", source="reuters.com",
                        source_tier="global_market_media", published_at="2026-10-15",
                        summary="BOJ menahan suku bunga.")
    prompt = build_user_prompt(build_dashboard_context(sample_report()), rules=load_rules(),
                               evidence=[item])
    assert "<evidence>" in prompt
    assert "Tulis `claims` untuk setiap klaim katalis" in prompt


def test_prompt_surfaces_detected_market_signals():
    context = build_dashboard_context(sample_report())
    numbers = {key: value for key, value in context.numbers().items() if value is not None}
    signalset = signals_module.detect_signals(numbers, report_date=context.report_date)
    prompt = build_user_prompt(context, rules=load_rules(), evidence=[], signals=signalset)
    assert "<market_signals>" in prompt
    assert "IHSG" in prompt, "sinyal IHSG yang material harus muncul di prompt"


def test_prompt_omits_signals_block_without_signals():
    prompt = build_user_prompt(build_dashboard_context(sample_report()), rules=load_rules())
    assert "<market_signals>" not in prompt


# ── evidence pipeline ───────────────────────────────────────────

def result(title: str, url: str, published: str, tier: str = "global_market_media",
           topics: tuple[str, ...] = ("fx",)) -> RawSearchResult:
    return RawSearchResult(title=title, url=url, source="contoh.id", published_at=published,
                           summary="Ringkasan konteks pasar.", source_tier=tier, topics=topics)


def test_evidence_filters_freshness_tier_and_duplicates():
    results = [
        result("Rupiah stabil", "https://bi.go.id/a?utm_source=x", "2026-10-15"),
        result("Rupiah stabil", "https://reuters.com/a", "2026-10-15"),
        result("Berita lama", "https://reuters.com/old", "2026-09-01"),
        result("Tanpa tanggal", "https://reuters.com/nd", ""),
        result("Tanggal masa depan", "https://reuters.com/future", "2026-10-20"),
        result("Sumber lemah", "https://blog.random.id/x", "2026-10-15", tier="secondary"),
        result("Sindikasi sama", "https://cnbc.com/a", "2026-10-15"),
    ]
    built = evidence_module.build_evidence(results, report_date="2026-10-16", topics=["fx"],
                                           lookback_days=3, min_source_tier="global_market_media")
    assert [item.evidence_id for item in built.items] == ["E1", "E2"]
    reasons = {row["reason"] for row in built.dropped}
    assert {"duplikat_judul", "di_luar_rentang", "tanpa_tanggal", "tanggal_masa_depan",
            "tier_secondary"} <= reasons


def test_evidence_respects_domain_quota_and_reports_relevance():
    results = [result(f"Berita {index}", f"https://reuters.com/{index}", "2026-10-16")
               for index in range(5)]
    built = evidence_module.build_evidence(results, report_date="2026-10-16", topics=["fx"],
                                           max_per_domain=2, max_items=8)
    assert len(built.items) == 2
    assert all(0 < item.relevance <= 1 for item in built.items)
    assert "kuota_domain" in {row["reason"] for row in built.dropped}


def test_topic_plan_reacts_to_payload_moves():
    assert evidence_module.topic_plan({"fx.usd_idr.change_pct": 0.4}) == ["fx"]
    topics = evidence_module.topic_plan({"market.ihsg.change_pct": -0.9,
                                         "commodities.brent.change_pct": 1.2,
                                         "coal.mtd_pct": 3.0})
    assert topics == ["indonesian_equity", "commodities"]


def test_verbatim_quote_check():
    item = evidence_module.EvidenceItem(evidence_id="E1", title="BI", url="https://bi.go.id/a",
                                        source="bi.go.id", summary="Bank Indonesia menjaga stabilitas rupiah.")
    assert evidence_module.quote_is_verbatim("menjaga stabilitas rupiah", [item]) is True
    assert evidence_module.quote_is_verbatim("pasti akan menguat", [item]) is False


# ── validator ───────────────────────────────────────────────────

def validate(output: dict, *, report: dict | None = None, evidence: list | None = None,
             rules=None):
    context = build_dashboard_context(report or sample_report())
    rules = rules or load_rules()
    registry = context.registry(allow_rounding=rules.flag("numbers.allow_display_rounding", True))
    return validators.validate_output(output=output, context=context, rules=rules,
                                      registry=registry, evidence=evidence or [])


def test_valid_output_passes():
    report = validate(good_output())
    assert report.passed is True
    assert report.narrative == GOOD_NARRATIVE


def test_invented_number_is_rejected():
    output = good_output(narrative=GOOD_NARRATIVE.replace("6.147", "6.500"))
    report = validate(output)
    assert report.passed is False
    assert "unknown_number" in {issue.code for issue in report.errors}


def test_wrong_direction_is_rejected():
    output = good_output(narrative=GOOD_NARRATIVE.replace("turun 0,75%", "naik 0,75%"))
    assert "sign_mismatch" in {issue.code for issue in validate(output).errors}


def test_numbers_used_must_match_payload():
    output = good_output(numbers_used=[{"key": "market.ihsg.last", "value": 9999},
                                       {"key": "tidak.ada", "value": 1}])
    codes = {issue.code for issue in validate(output).errors}
    assert {"numbers_used_mismatch", "numbers_used_unknown_key"} <= codes


def test_numbers_used_accepts_display_rounding_only():
    rounded = good_output(numbers_used=[{"key": "fx.usd_idr.last", "value": 17903}])
    assert validate(rounded).passed is True
    report = validate(good_output(numbers_used=[{"key": "fx.usd_idr.last", "value": 17900}]))
    assert [issue.code for issue in report.errors] == ["numbers_used_mismatch"]


def test_claim_without_evidence_is_rejected():
    output = good_output(narrative=GOOD_NARRATIVE,
                         claims=[{"claim_id": "C1", "text": "Rupiah melemah karena arus keluar.",
                                  "type": "causal", "evidence_ids": []}])
    report = validate(output)
    assert report.passed is False
    assert report.claims[0].rejected_reason == "klaim_tanpa_bukti"


def test_causal_claim_needs_supporting_source():
    weak = evidence_module.EvidenceItem(evidence_id="E1", title="Blog", url="https://blog.id/a",
                                        source="blog.id", source_tier="secondary",
                                        summary="Komentar pasar.")
    output = good_output(narrative=GOOD_NARRATIVE,
                         claims=[{"claim_id": "C1", "text": "Rupiah melemah karena arus keluar.",
                                  "type": "causal", "evidence_ids": ["E1"]}])
    report = validate(output, evidence=[weak])
    assert report.claims[0].rejected_reason == "kausalitas_tanpa_sumber_pendukung"


def test_quote_not_found_in_evidence_is_rejected():
    output = good_output(narrative=GOOD_NARRATIVE + ' Bank Indonesia menyebut "pasti akan menguat tajam".')
    assert "quote_not_verbatim" in {issue.code for issue in validate(output).errors}


def test_style_limits_come_from_policy():
    many_sentences = " ".join(["IHSG bergerak mendatar pada sesi ini." for _ in range(12)])
    assert "too_many_sentences" in {issue.code for issue in validate(good_output(narrative=many_sentences)).errors}

    too_long = " ".join(["IHSG bergerak mendatar pada sesi ini dan pasar menunggu katalis berikutnya."] * 35)
    assert "too_many_words" in {issue.code for issue in validate(good_output(narrative=too_long)).errors}


def test_short_narrative_is_rejected():
    assert "too_short" in {issue.code for issue in validate(good_output(narrative="IHSG turun 0,75%.")).errors}


# ── engine ──────────────────────────────────────────────────────

def test_engine_publishes_then_serves_from_cache(tmp_path):
    llm = FakeLLMProvider([json.dumps(good_output())])
    engine = engine_with(tmp_path, [], llm=llm)
    request = NarrativeRequest(page=NarrativePage.DASHBOARD)

    first = engine.generate(request)
    assert first.status is NarrativeStatus.PUBLISHED
    assert first.narrative == GOOD_NARRATIVE
    assert first.validation["passed"] is True
    assert len(llm.calls) == 1

    second = engine.generate(request)
    assert second.status is NarrativeStatus.PUBLISHED
    assert len(llm.calls) == 1, "hasil kedua harus berasal dari cache, bukan panggilan baru"


def test_engine_writes_audit_trail(tmp_path):
    engine = engine_with(tmp_path, [], llm=FakeLLMProvider([json.dumps(good_output())]))
    engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    rows = audit.recent_records(directory=Path(tmp_path / "runtime-narrative" / "audit"))
    assert rows and rows[0]["status"] == "published"
    assert rows[0]["page"] == "dashboard"
    assert rows[0]["evidence_count"] == 0
    assert "rules_hash" in rows[0]


def test_engine_repairs_then_falls_back_on_invalid_numbers(tmp_path):
    bad = json.dumps(good_output(narrative=GOOD_NARRATIVE.replace("6.147", "6.500")))
    llm = FakeLLMProvider([bad, bad])
    engine = engine_with(tmp_path, [], llm=llm)
    result = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result.status is NarrativeStatus.FALLBACK
    assert result.reason == "validation_rejected"
    assert len(llm.calls) == 2, "satu percobaan awal + satu perbaikan sesuai max_repair_attempts"
    assert result.narrative, "fallback tetap menampilkan narasi deterministik"


def test_engine_fallback_is_cached_so_no_repeated_calls(tmp_path):
    bad = json.dumps(good_output(narrative=GOOD_NARRATIVE.replace("6.147", "6.500")))
    llm = FakeLLMProvider([bad, bad, bad, bad])
    engine = engine_with(tmp_path, [], llm=llm)
    engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    calls_after_first = len(llm.calls)
    engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert len(llm.calls) == calls_after_first


def test_engine_without_provider_uses_deterministic_fallback(tmp_path):
    engine = engine_with(tmp_path, [], llm=NullLLMProvider("belum dikonfigurasi"))
    result = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result.status is NarrativeStatus.FALLBACK
    assert result.reason == "provider_unavailable"
    assert result.narrative


def test_engine_provider_failure_is_not_labelled_validation_rejected(tmp_path):
    llm = FakeLLMProvider(error=ProviderUnavailableError("Provider sedang tidak tersedia (HTTP 500)."))
    engine = engine_with(tmp_path, [], llm=llm)
    result = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result.status is NarrativeStatus.FALLBACK
    assert result.reason == "provider_unavailable"
    assert result.narrative
    assert len(llm.calls) == 2, "dua percobaan singkat lalu menyerah, bukan kegagalan validasi"


def test_engine_stops_retrying_when_provider_requests_long_delay(tmp_path):
    error = ProviderUnavailableError("Provider sedang tidak tersedia (HTTP 429): Daily token limit exceeded.")
    error.retry_after = 3600
    llm = FakeLLMProvider(error=error)
    engine = engine_with(tmp_path, [], llm=llm)
    result = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result.reason == "provider_unavailable"
    assert len(llm.calls) == 1, "Retry-After panjang harus menghentikan percobaan ulang"


def test_engine_degrades_gracefully_when_search_fails(tmp_path):
    failing = FakeSearchProvider(error=RuntimeError("jaringan mati"))
    engine = engine_with(tmp_path, [], llm=FakeLLMProvider([json.dumps(good_output())]), search=failing)
    result = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result.status is NarrativeStatus.PUBLISHED
    assert any("Konteks eksternal tidak tersedia" in note for note in result.notes)


def test_engine_uses_evidence_and_reports_sources(tmp_path):
    evidence = result("Bank Indonesia menjaga stabilitas rupiah", "https://bi.go.id/siaran",
                      "2026-10-16", tier="official_primary", topics=())
    search = FakeSearchProvider([evidence])
    output = good_output(claims=[{"claim_id": "C1", "type": "statement",
                                  "text": "Bank Indonesia menyatakan komitmen stabilitas.",
                                  "evidence_ids": ["E1"]}])
    engine = engine_with(tmp_path, [], llm=FakeLLMProvider([json.dumps(output)]), search=search)
    result_ = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result_.status is NarrativeStatus.PUBLISHED
    assert result_.sources and result_.sources[0]["evidence_id"] == "E1"
    assert search.calls, "pencarian bukti seharusnya dipanggil untuk pergerakan yang ada"
    assert search.calls[0]["queries"], "kueri dinamis dari sinyal harus diteruskan ke pencarian"


def test_engine_latest_never_calls_llm(tmp_path):
    llm = FakeLLMProvider([json.dumps(good_output())])
    engine = engine_with(tmp_path, [], llm=llm)
    result = engine.latest(NarrativePage.DASHBOARD, "report-1")
    assert result.status is NarrativeStatus.FALLBACK
    assert llm.calls == []


def test_engine_unknown_page_report_is_unavailable(tmp_path):
    engine = NarrativeEngine(rules=load_rules(), llm=FakeLLMProvider(), search=FakeSearchProvider(),
                             cache=NarrativeCache(tmp_path / "cache"),
                             ledger=UsageLedger(tmp_path / "usage"),
                             report_loader=lambda: None, equity_loader=lambda: {})
    result = engine.latest(NarrativePage.DASHBOARD, "")
    assert result.status is NarrativeStatus.UNAVAILABLE


def test_engine_respects_daily_call_limit(tmp_path, monkeypatch):
    monkeypatch.setenv("LLM_MAX_CALLS_PER_DAY_TEST", "1")
    rules = load_rules()
    values = {name: dict(items) for name, items in rules.values.items()}
    values["cost"]["max_calls_per_day"] = 0
    from market_report.domain.narrative_rules import RuleSet

    limited = RuleSet(values=values, rules_hash="test", rules_path=rules.rules_path)
    engine = engine_with(tmp_path, [], llm=FakeLLMProvider([json.dumps(good_output())]), rules=limited)
    result = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result.status is NarrativeStatus.FALLBACK
    assert result.reason == "budget_exhausted"


def test_refresh_job_generates_both_pages_with_respect_to_call_limit(tmp_path, monkeypatch):
    from market_report.services.narration import jobs

    llm = FakeLLMProvider([json.dumps(good_output())])
    engine = engine_with(tmp_path, [], llm=llm)
    monkeypatch.setattr(engine, "context_for", engine.context_for)
    results = jobs.refresh_narratives([NarrativePage.DASHBOARD, NarrativePage.EQUITY_SNAPSHOT],
                                      engine=engine)
    assert len(results) == 2, "batas default cost.max_calls_per_refresh mengizinkan dua halaman"
    assert [result.page for result in results] == [NarrativePage.DASHBOARD,
                                                   NarrativePage.EQUITY_SNAPSHOT]


def test_refresh_job_never_raises_when_engine_fails(tmp_path):
    from market_report.services.narration import jobs

    engine = engine_with(tmp_path, [], llm=FakeLLMProvider())

    def explode(**_kwargs):
        raise RuntimeError("pipeline rusak")

    engine.generate = explode  # type: ignore[assignment]
    assert jobs.refresh_narratives([NarrativePage.DASHBOARD], engine=engine) == [], (
        "kegagalan narasi tidak boleh menaikkan error ke worker")


def test_engine_survives_broken_context_loader(tmp_path):
    engine = engine_with(tmp_path, [], llm=FakeLLMProvider([json.dumps(good_output())]))
    engine.context_for = lambda *_args, **_kwargs: (_ for _ in ()).throw(RuntimeError("loader rusak"))
    result = engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD))
    assert result.status is NarrativeStatus.FALLBACK
    assert result.reason == "context_unavailable"


def test_stale_pages_reports_missing_narrative(tmp_path):
    from market_report.services.narration import jobs

    engine = engine_with(tmp_path, [], llm=FakeLLMProvider())
    assert jobs.stale_pages(engine, [NarrativePage.DASHBOARD]) == [NarrativePage.DASHBOARD]

    engine.cache.put(engine.generate(NarrativeRequest(page=NarrativePage.DASHBOARD, allow_search=False)),
                     key="manual", ttl_minutes=60)
    assert jobs.stale_pages(engine, [NarrativePage.DASHBOARD]) == []


def test_cache_key_changes_with_rules_and_model(tmp_path):
    base = dict(page=NarrativePage.DASHBOARD, report_id="r1", context_hash="h", rules_hash="r",
                provider="openai-compatible", model="m")
    assert cache_key(**base) != cache_key(**{**base, "model": "m2"})
    assert cache_key(**base) != cache_key(**{**base, "rules_hash": "r2"})


def test_breaker_opens_after_repeated_failures(tmp_path):
    from market_report.services.narration.breaker import CircuitBreaker

    breaker = CircuitBreaker("test", threshold=2, directory=tmp_path)
    assert breaker.is_open() is False
    breaker.record_failure()
    assert breaker.is_open() is False
    breaker.record_failure()
    assert breaker.is_open() is True
    breaker.reset()
    assert breaker.is_open() is False
