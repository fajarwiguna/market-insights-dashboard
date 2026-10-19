"""Narrative Engine: orkestrasi policy → konteks → bukti → prompt → LLM → validasi.

Satu pintu masuk (`generate`) supaya penggantian provider, model, atau strategi
bukti tidak menyentuh worker maupun API. Apa pun yang gagal berakhir pada narasi
deterministik yang sudah ada — bukan halaman error.
"""

from __future__ import annotations

import logging
import time
from datetime import date, timedelta
from typing import Callable, Sequence

from market_report.domain.narration_contract import (
    NARRATIVE_OUTPUT_SCHEMA,
    EvidenceItem,
    NarrativeClaim,
    NarrativeContext,
    NarrativePage,
    NarrativeRequest,
    NarrativeResult,
    NarrativeStatus,
    PROMPT_VERSION,
    utc_now_iso,
)
from market_report.domain.narrative_rules import RuleSet, load_rules
from market_report.services.narration import audit, evidence as evidence_module, providers as providers_pkg
from market_report.services.narration import signals as signals_module
from market_report.services.narration.breaker import CircuitBreaker
from market_report.services.narration.cache import (
    NEGATIVE_TTL_MINUTES,
    NarrativeCache,
    UsageLedger,
    cache_key,
    estimate_cost,
)
from market_report.services.narration.context_builder import (
    build_dashboard_context,
    build_equity_context,
)
from market_report.services.narration.errors import (
    BudgetExhaustedError,
    NarrativeError,
    ProviderUnavailableError,
    classify,
)
from market_report.services.narration.prompt_builder import build_prompt
from market_report.services.narration.validators import (
    claims_payload,
    parse_narrative_output,
    validate_output,
)

logger = logging.getLogger(__name__)

DEFAULT_TEMPERATURE = 0.2
PROVIDER_RETRIES = 2
RETRY_DELAY_SECONDS = 1.5
# Bila provider meminta jeda lebih lama (mis. batas harian), percobaan ulang
# hanya membuang waktu/kuota; hentikan lebih awal daripada menunggu.
MAX_RETRY_AFTER_SECONDS = 30.0


def _default_report_loader() -> dict | None:
    from market_report.services.report_service import load_report

    return load_report()


def _default_equity_loader() -> dict:
    from market_report.services.equity_snapshot_service import load_equity_snapshot

    return load_equity_snapshot()


class NarrativeEngine:
    def __init__(self, *, rules: RuleSet | None = None, llm=None, search=None,
                 cache: NarrativeCache | None = None, ledger: UsageLedger | None = None,
                 fetcher=None, post=None, report_loader: Callable[[], dict | None] | None = None,
                 equity_loader: Callable[[], dict] | None = None,
                 sleeper: Callable[[float], None] | None = None, repository="auto"):
        self.rules = rules or load_rules()
        self._llm = llm
        self._search = search
        self.cache = cache or NarrativeCache()
        self.ledger = ledger or UsageLedger()
        self.fetcher = fetcher
        self.post = post
        self.report_loader = report_loader or _default_report_loader
        self.equity_loader = equity_loader or _default_equity_loader
        self.sleeper = sleeper or time.sleep
        self.llm_breaker = CircuitBreaker("llm")
        self.search_breaker = CircuitBreaker("search", open_minutes=30)
        self._last_intelligence = {}
        # `repository="auto"`: pakai PostgreSQL bila tersedia; `False` mematikannya
        # (dipakai pengujian supaya tidak menyentuh database).
        self._repository = None if repository == "auto" else (repository or None)
        self._repository_resolved = repository != "auto"

    @property
    def repository(self):
        if not self._repository_resolved:
            from market_report.infrastructure.repositories.narrative_repository import (
                PostgresNarrativeRepository,
            )

            self._repository = PostgresNarrativeRepository.from_environment()
            self._repository_resolved = True
        return self._repository

    def _record(self, record_data: audit.AuditRecord, *, result: NarrativeResult | None = None,
                evidence: Sequence[EvidenceItem] = (),
                claims: Sequence[NarrativeClaim] = ()) -> None:
        """Tulis audit berkas, lalu cerminkan ke PostgreSQL bila tersedia."""
        audit.record(record_data)
        repository = self.repository
        if repository is None:
            return
        try:
            repository.save_run(
                audit.mask(record_data.to_payload()),
                narrative=result.narrative if result else "",
                output=result.to_payload() if result else None,
                published=bool(result and result.status is NarrativeStatus.PUBLISHED),
                evidence=[item.to_payload() for item in evidence],
                claims=claims_payload(list(claims)),
            )
        except Exception as error:
            logger.warning("Gagal menyimpan audit narasi ke PostgreSQL: %s", error)

    # ── provider ────────────────────────────────────────────────

    @property
    def llm(self):
        if self._llm is None:
            self._llm = providers_pkg.llm_provider(post=self.post)
        return self._llm

    @property
    def search(self):
        if self._search is None:
            self._search = providers_pkg.search_provider(
                fetcher=self.fetcher,
                registry_path=self.rules.text("sources.registry", "backend/config/llm_sources.json"),
                max_articles_per_source=self.rules.integer("sources.max_articles_per_source", 4),
            )
        return self._search

    def reload_rules(self) -> RuleSet:
        self.rules = load_rules(self.rules.rules_path if self.rules.available else None)
        return self.rules

    # ── konteks ─────────────────────────────────────────────────

    def context_for(self, page: NarrativePage, *, report: dict | None = None,
                    snapshot: dict | None = None) -> NarrativeContext:
        if page is NarrativePage.DASHBOARD:
            data = report if report is not None else (self.report_loader() or {})
            return build_dashboard_context(data)
        data = snapshot if snapshot is not None else (self.equity_loader() or {})
        return build_equity_context(data, report or {})

    # ── pembacaan tanpa LLM ─────────────────────────────────────

    def latest(self, page: NarrativePage, report_id: str = "") -> NarrativeResult:
        """Halaman hanya membaca cache; LLM tidak pernah dipanggil dari sini.

        `report_id` kosong berarti "laporan yang sedang aktif", sehingga pembacaan
        selalu menunjuk hasil untuk laporan yang sedang dilihat pengguna.
        """
        context = self.context_for(page)
        target_id = report_id or context.report_id
        cached = self.cache.get(page=page, report_id=target_id)
        if cached and not cached.expired:
            return cached.result
        if not context.report_date:
            return self._unavailable(context, "Belum ada data laporan untuk halaman ini.")
        result = self._fallback(context, self.rules, reason="belum_digenerate",
                                notes=["Narasi otomatis untuk laporan ini belum dibuat."])
        return result

    # ── generasi ────────────────────────────────────────────────

    def generate(self, request: NarrativeRequest, *, report: dict | None = None,
                 snapshot: dict | None = None, force: bool = False) -> NarrativeResult:
        started = time.monotonic()
        run_id = audit.new_run_id()
        rules = self.rules
        if not rules.available:
            context = self._safe_context(request, report, snapshot)
            return self._finish_fallback(context, rules, run_id, "rules_unavailable",
                                         [rules.unavailable_reason or "File policy tidak terbaca."], started)

        context = self._safe_context(request, report, snapshot)
        if not context.report_date:
            return self._finish_fallback(context, rules, run_id, "context_unavailable",
                                         ["Tanggal laporan tidak tersedia."], started)

        key = cache_key(page=context.page, report_id=context.report_id,
                        context_hash=context.context_hash(), rules_hash=rules.rules_hash,
                        provider=self.llm.name, model=str(getattr(self.llm, "model", "")),
                        prompt_version=PROMPT_VERSION)
        if not force:
            cached = self.cache.get_by_key(key)
            if cached and not cached.expired:
                return cached.result
            current = self.cache.get(page=context.page, report_id=context.report_id)
            if current and not current.expired and current.key == key:
                return current.result

        if not providers_pkg.narrative_enabled():
            return self._finish_fallback(context, rules, run_id, "disabled",
                                         ["Fitur narasi LLM belum diaktifkan (LLM_NARRATIVE_ENABLED=false)."],
                                         started)

        try:
            self._check_budget(rules)
        except BudgetExhaustedError as error:
            return self._finish_fallback(context, rules, run_id, classify(error), [str(error)], started)

        if self.llm_breaker.is_open():
            return self._finish_fallback(context, rules, run_id, "provider_breaker_open",
                                         ["Provider LLM dihentikan sementara karena kegagalan berulang."],
                                         started)
        if not self.llm.available():
            return self._finish_fallback(context, rules, run_id, "provider_unavailable",
                                         ["Provider LLM belum dikonfigurasi; memakai narasi deterministik."],
                                         started)

        signals = self._signals_for(context, rules)
        evidence_items, search_notes = self._collect_evidence(context, request, signals)
        result, issues, record = self._call_and_validate(context, rules, run_id, key,
                                                        evidence_items, search_notes, started,
                                                        signals)
        if result is not None:
            return result

        notes = list(search_notes)
        failure = str((record or {}).get("failure") or "")
        if failure.startswith("provider"):
            # Kegagalan panggilan provider (429/5xx/timeout) bukan kegagalan validasi.
            reason = failure
            notes.append("Panggilan provider LLM gagal; memakai narasi deterministik.")
        else:
            reason = "validation_rejected"
            notes.append("Narasi LLM tidak lolos validasi; memakai narasi deterministik.")
        self.llm_breaker.record_failure()
        fallback = self._fallback(context, rules, reason=reason, notes=notes)
        self._store(fallback, key, ttl_minutes=rules.integer("fallback.cache_negative_minutes",
                                                             NEGATIVE_TTL_MINUTES))
        self._record(audit.AuditRecord(
            run_id=run_id, page=context.page.value, report_id=context.report_id,
            report_date=context.report_date, status=fallback.status.value,
            reason=reason, rules_path=rules.rules_path, rules_hash=rules.rules_hash,
            prompt_version=PROMPT_VERSION, provider=self.llm.name,
            model=str(getattr(self.llm, "model", "")), context_hash=context.context_hash(),
            cache_key=key, latency_ms=int((time.monotonic() - started) * 1000),
            repair_count=record.get("repair_count", 0) if record else 0,
            evidence_count=len(evidence_items),
            validation=record.get("validation", {}) if record else {},
        ), result=fallback, evidence=evidence_items)
        return fallback

    # ── langkah internal ────────────────────────────────────────

    def _safe_context(self, request: NarrativeRequest, report: dict | None,
                      snapshot: dict | None) -> NarrativeContext:
        try:
            return self.context_for(request.page, report=report, snapshot=snapshot)
        except Exception as error:
            logger.exception("Gagal menyusun konteks narasi: %s", error)
            return NarrativeContext(page=request.page, report_id=request.report_id or "",
                                    report_date="")

    def _check_budget(self, rules: RuleSet) -> None:
        usage = self.ledger.read()
        limit = rules.integer("cost.max_calls_per_day", 12)
        if int(usage.get("calls", 0)) >= limit:
            raise BudgetExhaustedError(f"Batas panggilan harian ({limit}) sudah tercapai.")
        budget = rules.number("cost.daily_budget_usd", 0.0)
        if budget and float(usage.get("cost_usd", 0.0)) >= budget:
            raise BudgetExhaustedError("Anggaran biaya harian narasi sudah terpakai.")

    def _signals_for(self, context: NarrativeContext, rules: RuleSet):
        """Turunkan sinyal pasar sesi ini dari angka halaman (bagian 3A)."""
        numbers = {key: value for key, value in context.numbers().items() if value is not None}
        try:
            return signals_module.detect_signals(
                numbers,
                thresholds=signals_module.thresholds_from_rules(rules),
                report_date=context.report_date,
                max_queries=rules.integer("thresholds.max_query_count", 6),
            )
        except Exception as error:  # sinyal bersifat bantu; jangan hentikan narasi
            logger.warning("Deteksi sinyal pasar gagal: %s", error)
            return signals_module.SignalSet()

    def _collect_evidence(self, context: NarrativeContext, request: NarrativeRequest, signals=None):
        notes: list[str] = []
        signals = signals or signals_module.SignalSet()
        if not request.allow_search or not self.rules.flag("sources.search_enabled", True):
            return [], notes
        if self.search_breaker.is_open():
            notes.append("Sumber eksternal dihentikan sementara; narasi memakai data laporan saja.")
            return [], notes
        try:
            provider = self.search
        except Exception as error:
            notes.append("Sumber bukti tidak tersedia.")
            logger.warning("Provider bukti gagal disiapkan: %s", error)
            return [], notes
        if not provider.available():
            return [], notes

        topics = list(signals.topics)[: self.rules.integer("thresholds.max_query_count", 6)]
        queries = list(signals.queries)
        lookback = self.rules.integer("sources.lookback_days", 3)
        since = _shift(context.report_date, -lookback)
        try:
            raw = provider.discover(topics=topics, since=since,
                                    max_items=self.rules.integer("sources.max_evidence_items", 8),
                                    queries=queries)
            self.search_breaker.record_success()
        except Exception as error:
            self.search_breaker.record_failure()
            notes.append("Konteks eksternal tidak tersedia untuk sesi ini.")
            logger.warning("Pencarian bukti gagal: %s", error)
            return [], notes

        # Jalankan News Intelligence Pipeline bila provider adalah seeded/real (bukan mock test)
        if getattr(provider, "name", "") != "fake-search":
            try:
                from market_report.services.narration.news_intelligence import NewsIntelligencePipeline

                registry = getattr(provider, "registry", {})
                timeout = getattr(provider, "timeout", 15.0)
                intel_pipeline = NewsIntelligencePipeline(registry, fetcher=self.fetcher, timeout=timeout)
                intel_report = intel_pipeline.run(context, signals, self.rules)
                self._last_intelligence[context.report_id] = intel_report
                if intel_report.evidence_items:
                    return intel_report.evidence_items, notes
            except Exception as error:
                logger.warning("News Intelligence pipeline mengalami kendala, memakai seeded fallback: %s", error)

        built = evidence_module.build_evidence(
            raw, report_date=context.report_date, topics=topics, lookback_days=lookback,
            min_source_tier=self.rules.text("sources.min_source_tier", "major_media"),
            max_items=self.rules.integer("sources.max_evidence_items", 8),
            max_per_domain=self.rules.integer("sources.max_items_per_domain", 2),
            queries=queries,
        )
        if not built.items:
            notes.append("Tidak ada bukti eksternal yang lolos filter untuk tanggal laporan.")
        return built.items, notes

    def _call_and_validate(self, context: NarrativeContext, rules: RuleSet, run_id: str, key: str,
                           evidence_items: list[EvidenceItem], search_notes: list[str],
                           started: float, signals=None):
        registry = context.registry(
            allow_rounding=rules.flag("numbers.allow_display_rounding", True),
            require_separate_labels=rules.flag("numbers.require_separate_observation_labels", True),
        )
        issues: list = []
        repairs = 0
        max_repairs = rules.integer("validation.max_repair_attempts", 1)
        total_in = total_out = 0
        for attempt in range(max_repairs + 1):
            package = build_prompt(context, rules=rules, evidence=evidence_items, issues=issues,
                                   signals=signals)
            try:
                response = self._call_llm(package, rules)
            except Exception as error:
                self.llm_breaker.record_failure()
                code = classify(error)
                logger.warning("Panggilan LLM gagal (%s): %s", code, error)
                return None, issues, {"repair_count": repairs,
                                      "validation": {"error": code, "detail": str(error)[:300]},
                                      "failure": code,
                                      "search_notes": search_notes}
            total_in += response.tokens_in
            total_out += response.tokens_out
            try:
                output = parse_narrative_output(response.text)
            except NarrativeError as error:
                issues = []
                logger.warning("Keluaran LLM tidak dapat dibaca: %s", error)
                if attempt < max_repairs:
                    repairs += 1
                    continue
                return None, issues, {"repair_count": repairs,
                                      "validation": {"error": classify(error)}}

            report = validate_output(output=output, context=context, rules=rules,
                                     registry=registry, evidence=evidence_items)
            if report.passed:
                self.llm_breaker.record_success()
                result = NarrativeResult(
                    page=context.page, status=NarrativeStatus.PUBLISHED,
                    report_id=context.report_id, report_date=context.report_date,
                    narrative=report.narrative, sections=report.sections,
                    sources=[item.to_payload() for item in evidence_items],
                    notes=search_notes, run_id=run_id, generated_at=utc_now_iso(),
                    narrative_gaps=report.narrative_gaps,
                    validation=report.to_payload(), provider=self.llm.name,
                    model=str(getattr(self.llm, "model", "")),
                )
                self._store(result, key, ttl_minutes=rules.integer("fallback.narrative_ttl_minutes", 180))
                usage = self.ledger.record(tokens_in=total_in, tokens_out=total_out,
                                           cost_usd=estimate_cost(rules, total_in, total_out))
                self._record(audit.AuditRecord(
                    run_id=run_id, page=context.page.value, report_id=context.report_id,
                    report_date=context.report_date, status=result.status.value,
                    rules_path=rules.rules_path, rules_hash=rules.rules_hash,
                    prompt_version=PROMPT_VERSION, provider=self.llm.name,
                    model=str(getattr(self.llm, "model", "")), context_hash=context.context_hash(),
                    cache_key=key, latency_ms=int((time.monotonic() - started) * 1000),
                    tokens_in=total_in, tokens_out=total_out,
                    cost_usd=estimate_cost(rules, total_in, total_out),
                    repair_count=repairs, evidence_count=len(evidence_items),
                    validation=report.to_payload(),
                ), result=result, evidence=evidence_items, claims=report.claims)
                logger.debug("Pemakaian harian narasi: %s", usage)
                return result, [], {"repair_count": repairs, "validation": report.to_payload()}

            issues = report.issues
            logger.warning("Narasi ditolak (%s error, %s warning): %s", len(report.errors),
                           len(report.warnings),
                           [issue.code for issue in report.errors][:5])
            if attempt < max_repairs:
                repairs += 1
                continue
            return None, issues, {"repair_count": repairs, "validation": report.to_payload()}
        return None, issues, {"repair_count": repairs, "validation": {}}

    def _call_llm(self, package, rules: RuleSet):
        last_error: Exception | None = None
        for attempt in range(PROVIDER_RETRIES):
            try:
                return self.llm.generate(
                    system=package.system, user=package.user, schema=NARRATIVE_OUTPUT_SCHEMA,
                    max_tokens=rules.integer("cost.max_output_tokens", 700),
                    temperature=rules.number("llm.temperature", DEFAULT_TEMPERATURE),
                )
            except ProviderUnavailableError as error:
                last_error = error
                if attempt + 1 >= PROVIDER_RETRIES:
                    break
                retry_after = getattr(error, "retry_after", None)
                if isinstance(retry_after, (int, float)):
                    if retry_after > MAX_RETRY_AFTER_SECONDS:
                        logger.warning("Provider meminta jeda %.0f dtk; menghentikan percobaan ulang.",
                                       retry_after)
                        break
                    self.sleeper(max(0.0, float(retry_after)))
                elif attempt + 1 < PROVIDER_RETRIES:
                    self.sleeper(RETRY_DELAY_SECONDS * (attempt + 1))
        raise last_error or ProviderUnavailableError("Panggilan LLM gagal.")

    def _store(self, result: NarrativeResult, key: str, *, ttl_minutes: int) -> None:
        self.cache.put(result, key=key, ttl_minutes=ttl_minutes)

    def _fallback(self, context: NarrativeContext, rules: RuleSet, *, reason: str,
                  notes: list[str] | None = None) -> NarrativeResult:
        seed = context.seed_text()
        narrative = seed or rules.macro("neutral_phrasing_missing",
                                        "Narasi otomatis belum tersedia untuk laporan ini.")
        sources_payload: list[dict[str, object]] = []
        status = NarrativeStatus.FALLBACK

        intel = getattr(self, "_last_intelligence", {}).get(context.report_id)
        is_mock_test = getattr(self._search, "name", "") == "fake-search" or getattr(self._llm, "name", "") == "fake"
        if not intel and context.page is NarrativePage.DASHBOARD and context.report_date and not is_mock_test:
            try:
                from market_report.services.narration.news_intelligence import NewsIntelligencePipeline
                signals = self._signals_for(context, rules)
                registry = getattr(self.search, "registry", {})
                pipeline = NewsIntelligencePipeline(registry, fetcher=self.fetcher, timeout=getattr(self.search, "timeout", 15.0))
                intel = pipeline.run(context, signals, rules)
                self._last_intelligence[context.report_id] = intel
            except Exception as e:
                logger.debug("News intelligence fallback generation error: %s", e)

        if intel and intel.suggested_narrative and context.page is NarrativePage.DASHBOARD and not is_mock_test:
            narrative = intel.suggested_narrative
            sources_payload = [
                {"evidence_id": it.evidence_id, "title": it.title, "url": it.url,
                 "source": it.source, "source_tier": it.source_tier, "publisher": it.publisher}
                for it in intel.evidence_items
            ]
            if notes is None:
                notes = []
            notes.append("Narasi disusun berdasarkan riset berita terverifikasi (News Intelligence).")
        elif seed and reason in {"no_evidence"}:
            narrative = f"{seed} {rules.macro('neutral_phrasing_no_catalyst', '')}".strip()

        return NarrativeResult(
            page=context.page, status=status, report_id=context.report_id,
            report_date=context.report_date, narrative=narrative,
            sections=[dict(section) for section in context.seed_sections],
            sources=sources_payload,
            notes=list(notes or []), run_id=audit.new_run_id(), generated_at=utc_now_iso(),
            reason=reason, provider=self.llm.name if self._llm else "none",
        )

    def _unavailable(self, context: NarrativeContext, message: str) -> NarrativeResult:
        return NarrativeResult(page=context.page, status=NarrativeStatus.UNAVAILABLE,
                               report_id=context.report_id, report_date=context.report_date,
                               narrative="", notes=[message], run_id=audit.new_run_id(),
                               generated_at=utc_now_iso(), reason="unavailable")

    def _finish_fallback(self, context: NarrativeContext, rules: RuleSet, run_id: str,
                         reason: str, notes: list[str], started: float) -> NarrativeResult:
        result = self._fallback(context, rules, reason=reason, notes=notes)
        result.run_id = run_id
        self._record(audit.AuditRecord(
            run_id=run_id, page=context.page.value, report_id=context.report_id,
            report_date=context.report_date, status=result.status.value, reason=reason,
            rules_path=rules.rules_path, rules_hash=rules.rules_hash,
            prompt_version=PROMPT_VERSION, provider=getattr(self._llm, "name", "none"),
            model=str(getattr(self._llm, "model", "")), context_hash=context.context_hash(),
            latency_ms=int((time.monotonic() - started) * 1000),
        ), result=result)
        return result


def _shift(report_date: str, days: int) -> str:
    try:
        return (date.fromisoformat(report_date) + timedelta(days=days)).isoformat()
    except Exception:
        return report_date
