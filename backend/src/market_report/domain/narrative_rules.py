"""Policy layer narasi LLM: membaca `llm_rules.md` menjadi RuleSet.

File policy adalah sumber kebenaran perilaku fitur narasi. Modul ini hanya
membaca dan mengetikkan nilai; ia tidak memanggil LLM maupun jaringan, dan
tidak pernah membuat narasi sendiri.

Aturan yang tercantum di `HARD_RULES` tidak bisa dilonggarkan dari file policy:
jika file mencoba menuliskannya lebih longgar, nilai paksa kode yang dipakai
dan penyimpangan itu dicatat pada `forced_keys`.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)

DEFAULT_RULES_FILENAME = "llm_rules.md"
_SECTION_RE = re.compile(r"^##\s*\[(?P<name>[A-Za-z_][A-Za-z0-9_]*)\]\s*$")
_MACRO_SECTION_RE = re.compile(r"^##\s*Macros\b", re.IGNORECASE)
_BULLET_RE = re.compile(r"^\s*[-*]\s*(?P<key>[A-Za-z_][A-Za-z0-9_]*)\s*:\s*(?P<value>.*?)\s*$")

# Nilai default: dipakai bila file tidak ada, tidak terbaca, atau sebuah kunci hilang.
DEFAULTS: dict[str, dict[str, object]] = {
    "global": {
        "language": "id",
        "tone": "objective",
        "style": "professional",
        "max_paragraphs": 1,
        "deductive": True,
        "forbid_promotional_language": True,
        "forbid_personal_opinion": True,
        "forbid_hyperbole": True,
    },
    "numbers": {
        "authoritative_source": "application_payload",
        "never_invent": True,
        "never_estimate": True,
        "never_round": True,
        "preserve_units": True,
        "preserve_sign": True,
        "preserve_dates": True,
        "allow_derived_arithmetic": False,
        "allow_display_rounding": True,
        "reject_on_mismatch": True,
        "require_separate_observation_labels": True,
    },
    "sources": {
        "mode": "seeded",
        "registry": "backend/config/llm_sources.json",
        "search_enabled": True,
        "require_source_for_external_claims": True,
        "min_source_tier": "major_media",
        "allow_secondary_for_causal_claims": False,
        "max_items_per_domain": 2,
        "reject_undated": True,
        "require_verbatim_quote_check": True,
        "lookback_days": 3,
        "max_evidence_items": 8,
        "max_articles_per_source": 4,
    },
    "macro": {
        "include_global_context": True,
        "include_domestic_context": True,
        "avoid_unsupported_causality": True,
        "causality_requires_explicit_source": True,
        "allowed_safe_connectives": ["seiring", "di tengah", "bertepatan dengan"],
    },
    "dashboard": {"max_sentences": 4, "max_words": 100, "must_cover": [], "forbidden_sections": []},
    "equity_snapshot": {"max_sentences": 3, "max_words": 80, "sections": [], "must_cover": []},
    "validation": {
        "number_validation": "required",
        "source_validation": "required",
        "date_validation": "required",
        "style_validation": "required",
        "claim_validation": "required",
        "max_repair_attempts": 1,
        "min_narrative_words": 25,
    },
    "fallback": {
        "on_llm_failure": "deterministic_seed",
        "on_search_failure": "dashboard_only",
        "on_no_evidence": "neutral_phrasing",
        "on_validation_failure": "deterministic_seed",
        "cache_negative_minutes": 30,
        "narrative_ttl_minutes": 180,
    },
    "cost": {
        "max_calls_per_refresh": 2,
        "max_calls_per_day": 12,
        "max_output_tokens": 700,
        "max_input_tokens": 6000,
        "daily_budget_usd": 1.0,
        # Harga per juta token; 0 berarti estimasi biaya tidak dihitung.
        "price_input_per_mtok": 0.0,
        "price_output_per_mtok": 0.0,
    },
    "llm": {"temperature": 0.2},
    "thresholds": {
        "query_material_pct": 0.5,
        "index_material_pct": 0.35,
        "fx_material_pct": 0.25,
        "commodity_material_pct": 0.5,
        "yield_material_bp": 3.0,
        "foreign_flow_material_idr_bn": 250,
        "capital_flow_material_usd_mn": 100,
        "max_query_count": 6,
        "queries_per_signal": 2,
    },
    "macros": {
        "neutral_phrasing_no_catalyst": "Belum terdapat katalis yang cukup kuat dari sumber yang tersedia.",
        "neutral_phrasing_stale": "Data terbaru untuk indikator ini belum tersedia pada tanggal laporan.",
        "neutral_phrasing_missing": "Angka untuk indikator ini belum tersedia pada data laporan.",
    },
}

# (section, key) -> nilai yang dipaksa kode. File policy tidak boleh melonggarkan ini.
HARD_RULES: dict[tuple[str, str], object] = {
    ("numbers", "never_invent"): True,
    ("numbers", "never_estimate"): True,
    ("numbers", "preserve_units"): True,
    ("numbers", "preserve_sign"): True,
    ("numbers", "preserve_dates"): True,
    ("numbers", "authoritative_source"): "application_payload",
    ("sources", "require_source_for_external_claims"): True,
    ("validation", "number_validation"): "required",
    ("validation", "source_validation"): "required",
    ("validation", "date_validation"): "required",
}


def _parse_scalar(text: str) -> object:
    low = text.lower()
    if low in ("true", "ya"):
        return True
    if low in ("false", "tidak"):
        return False
    if low in ("null", "none"):
        return None
    if re.fullmatch(r"-?\d+", text):
        return int(text)
    if re.fullmatch(r"-?\d+\.\d+", text):
        return float(text)
    return text


def _parse_value(raw: str) -> object:
    text = raw.strip()
    if len(text) >= 2 and text.startswith("[") and text.endswith("]"):
        inner = text[1:-1].strip()
        if not inner:
            return []
        return [_parse_scalar(part.strip().strip("\"'")) for part in inner.split(",") if part.strip()]
    return _parse_scalar(text.strip("\"'"))


def parse_rules_text(text: str) -> tuple[dict[str, dict[str, object]], tuple[str, ...]]:
    """Parse isi file policy. Kembalikan (nilai, kunci_tak_dikenal).

    Mendukung dua bentuk nilai list supaya policy tetap enak ditulis manusia:

        - sections: [market, sector]      (satu baris)
        - must_cover:                     (daftar bertingkat)
          - index
          - foreign_flow

    Untuk bentuk bertingkat, baris `- item` yang menjorok (indentasi) setelah
    sebuah `- key:` tanpa nilai dikumpulkan sebagai isi list kunci tersebut.
    """
    values: dict[str, dict[str, object]] = {}
    unknown: list[str] = []
    section: str | None = None
    pending: tuple[str, str] | None = None
    for line in text.splitlines():
        section_match = _SECTION_RE.match(line)
        if section_match:
            section = section_match.group("name").lower()
            values.setdefault(section, {})
            pending = None
            continue
        if line.startswith("##"):
            section = "macros" if _MACRO_SECTION_RE.match(line) else None
            if section:
                values.setdefault(section, {})
            pending = None
            continue
        if section is None:
            continue
        stripped = line.strip()
        if not stripped.startswith(("-", "*")):
            pending = None
            continue
        content = stripped[1:].strip()
        indented = bool(line[:1]) and line[0] in (" ", "\t")
        if pending is not None and indented and content:
            # Baris item milik daftar `- key:` di atasnya.
            target_section, target_key = pending
            current = values.get(target_section, {}).get(target_key)
            if not isinstance(current, list):
                current = []
            current.append(_parse_scalar(content.strip("\"'")))
            values.setdefault(target_section, {})[target_key] = current
            continue
        bullet = _BULLET_RE.match(line)
        if bullet:
            key = bullet.group("key").lower()
            raw_value = bullet.group("value").strip()
            if raw_value:
                values[section][key] = _parse_value(raw_value)
                pending = None
            else:
                # Nilai list ditulis sebagai baris-baris berikutnya.
                values[section][key] = []
                pending = (section, key)
            continue
        if content:
            unknown.append(f"{section}:{stripped[:60]}")
        pending = None
    return values, tuple(unknown)


@dataclass(frozen=True)
class RuleSet:
    """Nilai policy efektif (default + file + aturan paksa kode)."""

    values: dict[str, dict[str, object]]
    rules_hash: str
    rules_path: str
    unknown_keys: tuple[str, ...] = ()
    forced_keys: tuple[str, ...] = ()
    available: bool = True
    unavailable_reason: str = ""

    def section(self, name: str) -> dict[str, object]:
        return dict(self.values.get(name) or {})

    def get(self, dotted: str, default: object = None) -> object:
        section, _, key = dotted.partition(".")
        value = (self.values.get(section) or {}).get(key)
        return default if value is None else value

    def number(self, dotted: str, default: float = 0.0) -> float:
        value = self.get(dotted, default)
        try:
            return float(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def integer(self, dotted: str, default: int = 0) -> int:
        value = self.get(dotted, default)
        try:
            return int(value)  # type: ignore[arg-type]
        except (TypeError, ValueError):
            return default

    def flag(self, dotted: str, default: bool = False) -> bool:
        value = self.get(dotted, default)
        return value if isinstance(value, bool) else default

    def text(self, dotted: str, default: str = "") -> str:
        value = self.get(dotted, default)
        return str(value) if value is not None else default

    def macro(self, name: str, default: str = "") -> str:
        return self.text(f"macros.{name}", default)

    def page_limits(self, page: str) -> tuple[int, int]:
        section = "dashboard" if page == "dashboard" else "equity_snapshot"
        return (
            self.integer(f"{section}.max_sentences", 4),
            self.integer(f"{section}.max_words", 100),
        )

    @classmethod
    def unavailable(cls, path: str, reason: str = "File policy tidak terbaca.") -> "RuleSet":
        return cls(values={name: dict(items) for name, items in DEFAULTS.items()},
                   rules_hash="unavailable", rules_path=path, forced_keys=(), available=False,
                   unavailable_reason=reason)


def _merge_defaults(values: dict[str, dict[str, object]]) -> dict[str, dict[str, object]]:
    merged: dict[str, dict[str, object]] = {name: dict(items) for name, items in DEFAULTS.items()}
    for name, items in values.items():
        merged.setdefault(name, {}).update(items)
    return merged


def _enforce_hard_rules(values: dict[str, dict[str, object]]) -> tuple[str, ...]:
    forced: list[str] = []
    for (section, key), required in HARD_RULES.items():
        current = (values.get(section) or {}).get(key)
        if current is None:
            values.setdefault(section, {})[key] = required
            continue
        if current != required:
            forced.append(f"{section}.{key}")
            logger.warning("Aturan %s.%s di file policy diabaikan; kode memaksa nilai %r.",
                           section, key, required)
            values[section][key] = required
    return tuple(forced)


def resolve_rules_path(configured: str | Path | None = None) -> Path:
    """Cari file policy: argumen (eksplisit) → LLM_RULES_FILE → backend/config → docs."""
    from market_report.config import project_root

    root = project_root()
    candidates: list[Path] = []
    if configured:
        # Path eksplisit dipakai apa adanya; bila tidak ada, dilaporkan sebagai
        # tidak tersedia alih-alih diam-diam memakai file policy repo.
        explicit = Path(configured)
        return explicit if explicit.is_absolute() else root / explicit
    env_path = os.environ.get("LLM_RULES_FILE", "").strip()
    if env_path:
        candidates.append(Path(env_path))
    candidates.append(root / "backend" / "config" / DEFAULT_RULES_FILENAME)
    candidates.append(root / "docs" / DEFAULT_RULES_FILENAME)
    for candidate in candidates:
        resolved = candidate if candidate.is_absolute() else root / candidate
        if resolved.is_file():
            return resolved
    return candidates[-1]


def load_rules(path: str | Path | None = None) -> RuleSet:
    """Baca file policy. Kegagalan apa pun menghasilkan RuleSet tidak tersedia."""
    resolved = resolve_rules_path(path)
    try:
        raw = resolved.read_bytes()
        text = raw.decode("utf-8")
    except OSError as error:
        logger.error("File policy narasi tidak terbaca (%s): %s", resolved, error)
        return RuleSet.unavailable(str(resolved), f"File policy tidak terbaca: {error.__class__.__name__}")
    values, unknown = parse_rules_text(text)
    merged = _merge_defaults(values)
    forced = _enforce_hard_rules(merged)
    digest = hashlib.sha256(raw).hexdigest()
    return RuleSet(values=merged, rules_hash=digest, rules_path=str(resolved),
                   unknown_keys=unknown, forced_keys=forced, available=True)


def rules_digest(rules: RuleSet) -> str:
    """Ringkasan pendek untuk log dan cache key."""
    return rules.rules_hash[:12] if rules.available else "unavailable"
