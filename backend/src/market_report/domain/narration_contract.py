"""Kontrak LLM Narrative Engine: tipe data yang dipakai lintas lapisan.

Modul ini hanya berisi tipe dan skema. Tidak ada I/O, tidak ada panggilan LLM,
sehingga kontrak bisa diuji dan dipakai bersama oleh worker, API, dan PDF.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from enum import Enum

from market_report.domain.number_registry import NumberEntry, NumberRegistry

PROMPT_VERSION = "v2"


class NarrativePage(str, Enum):
    DASHBOARD = "dashboard"
    EQUITY_SNAPSHOT = "equity_snapshot"

    @classmethod
    def parse(cls, value: str) -> "NarrativePage":
        normalized = (value or "").strip().lower().replace("-", "_")
        aliases = {"equity": cls.EQUITY_SNAPSHOT, "equitysnapshot": cls.EQUITY_SNAPSHOT,
                   "main": cls.DASHBOARD, "home": cls.DASHBOARD}
        if normalized in aliases:
            return aliases[normalized]
        return cls(normalized)


class NarrativeStatus(str, Enum):
    PUBLISHED = "published"      # hasil LLM lulus validasi
    FALLBACK = "fallback"        # narasi deterministik dipakai
    STALE = "stale"              # hasil dari laporan sebelumnya
    UNAVAILABLE = "unavailable"  # tidak ada apa pun yang bisa ditampilkan


class ClaimType(str, Enum):
    FIGURE = "figure"
    STATEMENT = "statement"
    CAUSAL = "causal"


TIER_ORDER = ("official_primary", "supranational_official", "company_primary", "data_portal",
              "id_market_media", "global_market_media", "major_media", "secondary")


def tier_rank(tier: str) -> int:
    """Peringkat tier: makin kecil makin tinggi kredibilitasnya."""
    try:
        return TIER_ORDER.index(tier)
    except ValueError:
        return len(TIER_ORDER)


@dataclass(frozen=True)
class EvidenceItem:
    evidence_id: str
    title: str
    url: str
    source: str
    source_tier: str = "secondary"
    published_at: str = ""
    fetched_at: str = ""
    event_key: str = ""
    summary: str = ""
    relevance: float = 0.0
    used_for: tuple[str, ...] = ()
    publisher: str = ""
    # Status verifikasi & hubungan waktu dengan pergerakan pasar (blueprint §3C).
    verified: bool = False
    relation: str = ""          # before | same_day | after | unknown
    confidence: float = 0.0     # 0..1, diturunkan dari tier, kebaruan, dan kecocokan kueri
    query: str = ""

    def prompt_block(self) -> str:
        """Baris bukti untuk prompt. Isi artikel diperlakukan sebagai data, bukan perintah."""
        stamp = self.published_at or "tanpa tanggal"
        label = self.publisher or self.source
        relation = f" waktu={self.relation}" if self.relation else ""
        return (f"[{self.evidence_id}] {self.title} — {label} ({stamp}) "
                f"tier={self.source_tier} keyakinan={self.confidence:.2f}{relation}\n{self.summary}")

    def to_payload(self) -> dict[str, object]:
        return {"evidence_id": self.evidence_id, "title": self.title, "url": self.url,
                "source": self.source, "source_tier": self.source_tier,
                "published_at": self.published_at, "relevance": round(self.relevance, 3),
                "event_key": self.event_key, "used_for": list(self.used_for),
                "publisher": self.publisher, "verified": self.verified,
                "relation": self.relation, "confidence": round(self.confidence, 3)}


@dataclass(frozen=True)
class NarrativeClaim:
    claim_id: str
    text: str
    claim_type: str = ClaimType.STATEMENT.value
    evidence_ids: tuple[str, ...] = ()
    accepted: bool = True
    rejected_reason: str = ""


@dataclass(frozen=True)
class NarrativeContext:
    """Angka + konteks satu halaman. Satu-satunya sumber angka untuk narasi."""

    page: NarrativePage
    report_id: str
    report_date: str
    entries: tuple[NumberEntry, ...] = ()
    seed_sections: tuple[dict[str, str], ...] = ()
    notes: tuple[str, ...] = ()
    equity: dict | None = None

    def numbers(self) -> dict[str, Decimal | None]:
        return {entry.key: entry.value for entry in self.entries}

    def units(self) -> dict[str, str]:
        return {entry.key: entry.unit for entry in self.entries}

    def as_of(self) -> dict[str, str]:
        return {entry.key: entry.as_of for entry in self.entries if entry.as_of}

    def registry(self, *, allow_rounding: bool = False,
                 require_separate_labels: bool = True) -> NumberRegistry:
        return NumberRegistry.from_entries(list(self.entries), allow_rounding=allow_rounding,
                                           require_separate_labels=require_separate_labels)

    def seed_text(self) -> str:
        return " ".join(section.get("text", "") for section in self.seed_sections).strip()

    def payload(self) -> dict[str, object]:
        """Struktur JSON yang diberikan ke LLM (angka, satuan, tanggal observasi)."""
        payload: dict[str, object] = {
            "page": self.page.value,
            "report_id": self.report_id,
            "report_date": self.report_date,
            "numbers": [entry.display() for entry in self.entries],
            "as_of": self.as_of(),
        }
        if self.equity:
            payload["equity_context"] = self.equity
        return payload

    def context_hash(self) -> str:
        raw = json.dumps(self.payload(), sort_keys=True, default=str, ensure_ascii=False)
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class NarrativeRequest:
    page: NarrativePage
    report_id: str | None = None
    allow_search: bool = True
    reason: str = "refresh"


@dataclass
class NarrativeResult:
    page: NarrativePage
    status: NarrativeStatus
    report_id: str = ""
    report_date: str = ""
    narrative: str = ""
    sections: list[dict[str, str]] = field(default_factory=list)
    sources: list[dict[str, object]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)
    run_id: str = ""
    generated_at: str = ""
    reason: str = ""
    narrative_gaps: list[str] = field(default_factory=list)
    validation: dict[str, object] = field(default_factory=dict)
    provider: str = ""
    model: str = ""
    frozen: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "page": self.page.value,
            "status": self.status.value,
            "report_id": self.report_id,
            "report_date": self.report_date,
            "narrative": self.narrative,
            "sections": self.sections,
            "sources": self.sources,
            "notes": self.notes,
            "run_id": self.run_id,
            "generated_at": self.generated_at,
            "narrative_gaps": self.narrative_gaps,
            "frozen": self.frozen,
            "validation": self.validation,
        }

    @classmethod
    def from_payload(cls, payload: dict) -> "NarrativeResult":
        return cls(
            page=NarrativePage.parse(str(payload.get("page") or "dashboard")),
            status=NarrativeStatus(str(payload.get("status") or "unavailable")),
            report_id=str(payload.get("report_id") or ""),
            report_date=str(payload.get("report_date") or ""),
            narrative=str(payload.get("narrative") or ""),
            sections=list(payload.get("sections") or []),
            sources=list(payload.get("sources") or []),
            notes=list(payload.get("notes") or []),
            run_id=str(payload.get("run_id") or ""),
            generated_at=str(payload.get("generated_at") or ""),
            narrative_gaps=list(payload.get("narrative_gaps") or []),
            frozen=bool(payload.get("frozen")),
            validation=dict(payload.get("validation") or {}),
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


NARRATIVE_OUTPUT_SCHEMA: dict[str, object] = {
    "type": "object",
    "additionalProperties": False,
    "required": ["schema_version", "page", "narrative", "claims", "numbers_used"],
    "properties": {
        "schema_version": {"type": "integer", "const": 1},
        "page": {"type": "string", "enum": ["dashboard", "equity_snapshot"]},
        "narrative": {"type": "string"},
        "sections": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["id", "title", "text"],
                "properties": {"id": {"type": "string"}, "title": {"type": "string"},
                               "text": {"type": "string"}},
            },
        },
        "claims": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["claim_id", "text", "type"],
                "properties": {
                    "claim_id": {"type": "string"},
                    "text": {"type": "string"},
                    "type": {"type": "string", "enum": ["figure", "statement", "causal"]},
                    "evidence_ids": {"type": "array", "items": {"type": "string"}},
                    "supports_causality": {"type": "boolean"},
                },
            },
        },
        "numbers_used": {
            "type": "array",
            "items": {
                "type": "object",
                "required": ["key", "value"],
                "properties": {"key": {"type": "string"}, "value": {"type": "number"},
                               "unit": {"type": "string"}, "as_of": {"type": "string"}},
            },
        },
        "narrative_gaps": {"type": "array", "items": {"type": "string"}},
    },
}
