"""Audit trail: alasan setiap narasi tercatat dan dapat ditelusuri.

Ditulis sebagai JSONL per bulan di `runtime/narrative/audit/`. Prompt lengkap
tidak disimpan (hanya hash) dan tidak ada kredensial yang ikut tercatat.
"""

from __future__ import annotations

import json
import logging
import os
import uuid
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from market_report.services.narration.cache import narrative_directory

logger = logging.getLogger(__name__)

_MASK_KEYS = {"api_key", "authorization", "token", "secret", "password", "bearer", "cookie"}
# `tokens_in`/`tokens_out` adalah angka pemakaian, bukan kredensial, jadi tidak disamarkan.
_SENSITIVE_SUFFIXES = ("_key", "_token", "_secret", "_password", "_credential")


def _is_sensitive(key: str) -> bool:
    lowered = str(key).lower()
    return lowered in _MASK_KEYS or lowered.endswith(_SENSITIVE_SUFFIXES)


def new_run_id() -> str:
    return uuid.uuid4().hex[:16]


@dataclass
class AuditRecord:
    run_id: str
    page: str
    report_id: str
    report_date: str
    status: str
    reason: str = ""
    rules_path: str = ""
    rules_hash: str = ""
    prompt_version: str = ""
    provider: str = ""
    model: str = ""
    context_hash: str = ""
    cache_key: str = ""
    latency_ms: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    repair_count: int = 0
    evidence_count: int = 0
    validation: dict = field(default_factory=dict)
    created_at: str = ""

    def __post_init__(self) -> None:
        if not self.created_at:
            self.created_at = datetime.now(timezone.utc).isoformat(timespec="seconds")

    def to_payload(self) -> dict:
        return {key: value for key, value in asdict(self).items() if value not in ("", None)}


def audit_directory() -> Path:
    configured = os.environ.get("NARRATIVE_AUDIT_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else narrative_directory() / path
    return narrative_directory() / "audit"


def mask(payload: dict) -> dict:
    """Buang nilai yang berpotensi sensitif dari catatan audit/log."""
    cleaned = {}
    for key, value in (payload or {}).items():
        if _is_sensitive(key):
            cleaned[key] = "***"
        elif isinstance(value, dict):
            cleaned[key] = mask(value)
        else:
            cleaned[key] = value
    return cleaned


def record(record_data: AuditRecord, directory: Path | None = None) -> Path | None:
    """Simpan satu baris audit; kegagalan penulisan tidak menggagalkan narasi."""
    folder = Path(directory) if directory else audit_directory()
    path = folder / f"{record_data.created_at[:7]}.jsonl"
    try:
        folder.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(mask(record_data.to_payload()), ensure_ascii=False) + "\n")
    except OSError as error:
        logger.warning("Gagal menulis audit narasi: %s", error)
        return None
    log_summary(record_data)
    return path


def log_summary(record_data: AuditRecord) -> None:
    """Satu baris ringkas per run agar operator bisa memeriksa tanpa membuka JSONL."""
    logger.info(
        "narration run page=%s report_id=%s status=%s reason=%s rules_hash=%s prompt=%s "
        "provider=%s model=%s ms=%s tokens=%s/%s evidence=%s repairs=%s run_id=%s",
        record_data.page, record_data.report_id or "-", record_data.status,
        record_data.reason or "-", (record_data.rules_hash or "-")[:12],
        record_data.prompt_version or "-", record_data.provider or "-", record_data.model or "-",
        record_data.latency_ms, record_data.tokens_in, record_data.tokens_out,
        record_data.evidence_count, record_data.repair_count, record_data.run_id,
    )


def recent_records(page: str = "", limit: int = 20, directory: Path | None = None) -> list[dict]:
    """Baca audit terbaru untuk ditampilkan pada endpoint operator."""
    folder = Path(directory) if directory else audit_directory()
    rows: list[dict] = []
    for path in sorted(folder.glob("*.jsonl"), reverse=True):
        try:
            for line in reversed(path.read_text(encoding="utf-8").splitlines()):
                if not line.strip():
                    continue
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if page and row.get("page") != page:
                    continue
                rows.append(row)
                if len(rows) >= limit:
                    return rows
        except OSError:
            continue
    return rows
