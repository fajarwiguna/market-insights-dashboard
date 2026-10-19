"""Validasi keluaran LLM sebelum ditampilkan atau dibekukan (blueprint §11–§13).

Validator tidak mempercayai LLM maupun prompt: ia membandingkan narasi dengan
registry angka payload, daftar bukti yang benar-benar ada, dan batas gaya dari
file policy. Kegagalan berarti "jangan tampilkan", bukan "tampilkan apa saja".
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field

from market_report.domain.narration_contract import (
    ClaimType,
    EvidenceItem,
    NarrativeClaim,
    NarrativeContext,
)
from market_report.domain.narrative_rules import RuleSet
from market_report.domain.number_registry import NumberRegistry, ValidationIssue
from market_report.services.narration import evidence as evidence_module

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_WORD_RE = re.compile(r"\b[\w’'-]+\b")
_QUOTE_RE = re.compile(r"[“\"](?P<quote>[^”\"]{15,300})[”\"]")

# Daftar kecil kata promosi/hiperbola yang dilarang policy gaya proyek.
_PROMO_WORDS = ("dijamin", "pasti untung", "cuan besar", "luar biasa", "fantastis",
                "wajib beli", "rekomendasi beli", "tidak mungkin gagal", "fenomenal")
_PREDICTION_WORDS = ("akan dipastikan", "dipastikan akan", "tidak mungkin turun",
                     "sudah pasti naik", "pasti akan")


@dataclass
class ValidationReport:
    passed: bool = False
    errors: list[ValidationIssue] = field(default_factory=list)
    warnings: list[ValidationIssue] = field(default_factory=list)
    claims: list[NarrativeClaim] = field(default_factory=list)
    narrative: str = ""
    sections: list[dict[str, str]] = field(default_factory=list)
    narrative_gaps: list[str] = field(default_factory=list)
    numbers_used: list[dict] = field(default_factory=list)
    quoted_unsupported: list[str] = field(default_factory=list)

    @property
    def issues(self) -> list[ValidationIssue]:
        return self.errors + self.warnings

    def to_payload(self) -> dict[str, object]:
        return {
            "passed": self.passed,
            "errors": [{"code": issue.code, "token": issue.token} for issue in self.errors],
            "warnings": [{"code": issue.code, "token": issue.token} for issue in self.warnings],
            "claims": [{"claim_id": claim.claim_id, "accepted": claim.accepted,
                        "reason": claim.rejected_reason} for claim in self.claims],
            "numbers_used": len(self.numbers_used),
        }


def parse_narrative_output(raw: str) -> dict:
    """Baca JSON keluaran LLM; toleran terhadap pagar kode, tegas terhadap sisanya."""
    from market_report.services.narration.errors import InvalidOutputError

    text = (raw or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
        text = re.sub(r"```\s*$", "", text).strip()
    if not text:
        raise InvalidOutputError("Keluaran LLM kosong.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as error:
        start, end = text.find("{"), text.rfind("}")
        if start == -1 or end <= start:
            raise InvalidOutputError("Keluaran LLM bukan JSON.") from error
        try:
            payload = json.loads(text[start:end + 1])
        except json.JSONDecodeError as nested:
            raise InvalidOutputError("Keluaran LLM bukan JSON yang valid.") from nested
    if not isinstance(payload, dict):
        raise InvalidOutputError("Keluaran LLM bukan objek JSON.")
    return payload


def _route(errors: list[ValidationIssue], warnings: list[ValidationIssue],
           issues: list[ValidationIssue]) -> None:
    """Tempatkan issue sesuai tingkat keparahannya (error menolak, warning memicu perbaikan)."""
    for issue in issues:
        (errors if issue.is_error else warnings).append(issue)


def _severity_for(rules: RuleSet, key: str) -> str:
    """Aturan yang berstatus `required` di policy menjadi penolakan, bukan peringatan."""
    return "error" if str(rules.text(key, "")).strip().lower() == "required" else "warning"


def _count_words(text: str) -> int:
    return len(_WORD_RE.findall(text or ""))


def _count_sentences(text: str) -> int:
    return len([part for part in _SENTENCE_SPLIT_RE.split((text or "").strip()) if part.strip()])


def _style_issues(text: str, rules: RuleSet, context: NarrativeContext,
                  severity: str) -> list[ValidationIssue]:
    issues: list[ValidationIssue] = []
    max_sentences, max_words = rules.page_limits(context.page.value)
    sentences = _count_sentences(text)
    words = _count_words(text)
    if sentences > max_sentences:
        issues.append(ValidationIssue("too_many_sentences", str(sentences),
                                      f"Narasi {sentences} kalimat, batas {max_sentences}.",
                                      severity=severity))
    if words > max_words:
        issues.append(ValidationIssue("too_many_words", str(words),
                                      f"Narasi {words} kata, batas {max_words}.", severity=severity))
    minimum = rules.integer("validation.min_narrative_words", 25)
    if words < minimum:
        issues.append(ValidationIssue("too_short", str(words),
                                      f"Narasi hanya {words} kata, minimum {minimum}.", severity=severity))
    lowered = (text or "").lower()
    if rules.flag("global.forbid_promotional_language", True):
        for word in _PROMO_WORDS:
            if word in lowered:
                issues.append(ValidationIssue("promotional_language", word,
                                              f"Frasa promosi '{word}' dilarang.", severity=severity))
    if rules.flag("global.forbid_hyperbole", True):
        for word in _PREDICTION_WORDS:
            if word in lowered:
                issues.append(ValidationIssue("unsupported_prediction", word,
                                              f"Pernyataan '{word}' menyiratkan kepastian.",
                                              severity="error"))
    paragraph_breaks = len([b for b in re.split(r"\n\s*\n", text or "") if b.strip()])
    if paragraph_breaks > rules.integer("global.max_paragraphs", 1):
        issues.append(ValidationIssue("too_many_paragraphs", str(paragraph_breaks),
                                      "Narasi lebih dari satu paragraf.", severity=severity))
    return issues


def _numbers_used_issues(numbers_used, registry: NumberRegistry, severity: str) -> list[ValidationIssue]:
    """Deklarasi `numbers_used` LLM harus cocok dengan data halaman (self-declaration check)."""
    issues: list[ValidationIssue] = []
    by_key = {entry.key: entry for entry in registry.entries}
    for row in numbers_used or []:
        if not isinstance(row, dict):
            continue
        key, value = str(row.get("key") or ""), row.get("value")
        entry = by_key.get(key)
        if entry is None or entry.value is None:
            issues.append(ValidationIssue("numbers_used_unknown_key", key,
                                          f"Key '{key}' tidak ada pada data halaman.", severity=severity))
            continue
        # Nilai yang ditulis ulang sesuai tampilan halaman tetap sah (toleransi pembulatan),
        # tetapi angka yang berbeda tetap ditolak.
        if not registry.matches_value(key, value):
            issues.append(ValidationIssue("numbers_used_mismatch", key,
                                          f"Nilai {key} pada numbers_used berbeda dari data halaman.",
                                          severity=severity))
    return issues


def _claim_issues(claims: list[NarrativeClaim], evidence: list[EvidenceItem], rules: RuleSet,
                  severity: str) -> list[NarrativeClaim]:
    by_id = {item.evidence_id: item for item in evidence}
    resolved: list[NarrativeClaim] = []
    require_causal = rules.flag("macro.causality_requires_explicit_source", True)
    allow_secondary = rules.flag("sources.allow_secondary_for_causal_claims", False)
    for claim in claims:
        unknown = [eid for eid in claim.evidence_ids if eid not in by_id]
        if claim.claim_type in (ClaimType.STATEMENT.value, ClaimType.CAUSAL.value) and not claim.evidence_ids:
            resolved.append(NarrativeClaim(claim.claim_id, claim.text, claim.claim_type,
                                           claim.evidence_ids, accepted=False,
                                           rejected_reason="klaim_tanpa_bukti"))
            continue
        if unknown:
            resolved.append(NarrativeClaim(claim.claim_id, claim.text, claim.claim_type,
                                           claim.evidence_ids, accepted=False,
                                           rejected_reason=f"bukti_tidak_ada:{','.join(unknown)}"))
            continue
        if claim.claim_type == ClaimType.CAUSAL.value and require_causal:
            items = [by_id[eid] for eid in claim.evidence_ids]
            if not any(evidence_module.supports_causality(item) for item in items) and not allow_secondary:
                resolved.append(NarrativeClaim(claim.claim_id, claim.text, claim.claim_type,
                                               claim.evidence_ids, accepted=False,
                                               rejected_reason="kausalitas_tanpa_sumber_pendukung"))
                continue
        resolved.append(claim)
    return resolved


def validate_output(*, output: dict, context: NarrativeContext, rules: RuleSet,
                    registry: NumberRegistry, evidence: list[EvidenceItem]) -> ValidationReport:
    """Periksa keluaran LLM: skema, angka, tanggal, gaya, klaim, dan kutipan."""
    report = ValidationReport()
    errors, warnings = report.errors, report.warnings

    page = str(output.get("page") or "")
    if page and page != context.page.value:
        errors.append(ValidationIssue("page_mismatch", page, "Halaman keluaran tidak sesuai permintaan."))
    narrative = output.get("narrative")
    if not isinstance(narrative, str) or not narrative.strip():
        errors.append(ValidationIssue("empty_narrative", "", "Narasi kosong."))
        return report
    report.narrative = narrative.strip()

    sections: list[dict[str, str]] = []
    for item in output.get("sections") or []:
        if not isinstance(item, dict) or not isinstance(item.get("text"), str):
            continue
        sections.append({"id": str(item.get("id") or ""), "title": str(item.get("title") or ""),
                         "text": item["text"].strip()})
    report.sections = sections
    report.narrative_gaps = [str(gap) for gap in (output.get("narrative_gaps") or []) if str(gap).strip()]
    report.numbers_used = [row for row in (output.get("numbers_used") or []) if isinstance(row, dict)]

    inspected = "\n\n".join([report.narrative] + [section["text"] for section in sections])

    number_severity = _severity_for(rules, "validation.number_validation")
    _route(errors, warnings, registry.validate(inspected))

    style_severity = _severity_for(rules, "validation.style_validation")
    _route(errors, warnings, _style_issues(report.narrative, rules, context, style_severity))

    numbers_severity = _severity_for(rules, "validation.number_validation")
    _route(errors, warnings, _numbers_used_issues(report.numbers_used, registry, numbers_severity))

    claims: list[NarrativeClaim] = []
    for index, row in enumerate(output.get("claims") or []):
        if not isinstance(row, dict):
            continue
        claim_type = str(row.get("type") or ClaimType.STATEMENT.value).lower()
        claims.append(NarrativeClaim(
            claim_id=str(row.get("claim_id") or f"C{index + 1}"),
            text=str(row.get("text") or ""),
            claim_type=claim_type,
            evidence_ids=tuple(str(eid) for eid in (row.get("evidence_ids") or [])),
        ))
    claim_severity = _severity_for(rules, "validation.claim_validation")
    claims = _claim_issues(claims, evidence, rules, claim_severity)
    report.claims = claims
    for claim in claims:
        if claim.accepted:
            continue
        _route(errors, warnings, [ValidationIssue(
            "claim_rejected", claim.claim_id,
            f"Klaim {claim.claim_id} ditolak: {claim.rejected_reason}.", severity=claim_severity)])

    if rules.flag("sources.require_verbatim_quote_check", True):
        for match in _QUOTE_RE.finditer(inspected):
            quote = match.group("quote")
            if not evidence_module.quote_is_verbatim(quote, evidence):
                report.quoted_unsupported.append(quote)
                _route(errors, warnings, [ValidationIssue(
                    "quote_not_verbatim", quote[:40],
                    "Kutipan langsung tidak ditemukan pada sumber bukti.", severity=claim_severity)])

    report.passed = not errors
    return report


def claims_payload(claims: list[NarrativeClaim]) -> list[dict[str, object]]:
    return [{"claim_id": claim.claim_id, "text": claim.text, "type": claim.claim_type,
             "evidence_ids": list(claim.evidence_ids), "accepted": claim.accepted,
             "rejected_reason": claim.rejected_reason} for claim in claims]
