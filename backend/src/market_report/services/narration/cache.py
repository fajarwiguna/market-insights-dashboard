"""Cache narasi + ledger pemakaian (blueprint §15 dan §20).

Halaman tidak pernah memicu LLM: pembacaan hanya melihat berkas di
`runtime/narrative/`. Cache key memuat rules_hash, prompt_version, dan model,
sehingga perubahan policy atau model otomatis membatalkan narasi lama.
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_report.domain.narration_contract import NarrativePage, NarrativeResult, PROMPT_VERSION

logger = logging.getLogger(__name__)

DEFAULT_TTL_MINUTES = 180
NEGATIVE_TTL_MINUTES = 30


def narrative_directory() -> Path:
    """Folder kerja narasi; berada di runtime agar tidak ikut tersimpan di repositori.

    `NARRATIVE_DIR` relatif dihitung dari akar proyek (bukan dari `runtime/`),
    supaya `NARRATIVE_DIR=runtime/narasi` tidak menjadi `runtime/runtime/narasi`.
    """
    from market_report.config import project_root, runtime_directory

    configured = os.environ.get("NARRATIVE_DIR", "").strip()
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_absolute() else project_root() / path
    return runtime_directory() / "narrative"


def cache_key(*, page: NarrativePage, report_id: str, context_hash: str, rules_hash: str,
              provider: str, model: str, prompt_version: str = PROMPT_VERSION) -> str:
    raw = "|".join([page.value, report_id, context_hash, rules_hash, provider, model, prompt_version])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass
class CacheEntry:
    result: NarrativeResult
    stored_at: datetime
    ttl_minutes: int
    key: str

    @property
    def expired(self) -> bool:
        return datetime.now(timezone.utc) > self.stored_at + timedelta(minutes=self.ttl_minutes)


def _write_json(path: Path, payload: dict) -> None:
    """Tulis atomik supaya pembaca tidak pernah melihat berkas setengah jadi."""
    path.parent.mkdir(parents=True, exist_ok=True)
    handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=path.parent,
                                         prefix=path.name, suffix=".tmp", delete=False)
    try:
        json.dump(payload, handle, ensure_ascii=False)
        handle.flush()
        os.fsync(handle.fileno())
    finally:
        handle.close()
    os.replace(handle.name, path)


class NarrativeCache:
    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else narrative_directory()

    # ── berkas per halaman + laporan ────────────────────────────

    def _current_path(self, page: NarrativePage, report_id: str) -> Path:
        safe_id = "".join(char for char in report_id if char.isalnum() or char in "-_.") or "unknown"
        return self.directory / "current" / page.value / f"{safe_id}.json"

    def _key_path(self, key: str) -> Path:
        return self.directory / "keys" / f"{key}.json"

    def put(self, result: NarrativeResult, *, key: str, ttl_minutes: int = DEFAULT_TTL_MINUTES) -> None:
        payload = {
            "key": key,
            "stored_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ttl_minutes": ttl_minutes,
            "result": result.to_payload(),
        }
        try:
            _write_json(self._key_path(key), payload)
            _write_json(self._current_path(result.page, result.report_id), payload)
        except OSError as error:  # cache gagal bukan alasan menggagalkan narasi
            logger.warning("Gagal menulis cache narasi: %s", error)

    def get(self, *, page: NarrativePage, report_id: str) -> CacheEntry | None:
        return self._read(self._current_path(page, report_id))

    def get_by_key(self, key: str) -> CacheEntry | None:
        return self._read(self._key_path(key))

    def _read(self, path: Path) -> CacheEntry | None:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except Exception as error:
            logger.warning("Cache narasi tidak terbaca (%s): %s", path.name, error)
            return None
        try:
            stored_at = datetime.fromisoformat(str(payload.get("stored_at")))
            if stored_at.tzinfo is None:
                stored_at = stored_at.replace(tzinfo=timezone.utc)
            return CacheEntry(result=NarrativeResult.from_payload(payload.get("result") or {}),
                              stored_at=stored_at,
                              ttl_minutes=int(payload.get("ttl_minutes") or DEFAULT_TTL_MINUTES),
                              key=str(payload.get("key") or ""))
        except Exception as error:
            logger.warning("Isi cache narasi tidak dikenali: %s", error)
            return None


class UsageLedger:
    """Catat pemakaian harian agar anggaran biaya dan batas panggilan dipatuhi."""

    def __init__(self, directory: Path | None = None):
        self.directory = Path(directory) if directory else narrative_directory() / "usage"

    def _path(self) -> Path:
        today = datetime.now(timezone.utc).date().isoformat()
        return self.directory / f"{today}.json"

    def read(self) -> dict:
        try:
            return json.loads(self._path().read_text(encoding="utf-8"))
        except Exception:
            return {"calls": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0}

    def record(self, *, tokens_in: int = 0, tokens_out: int = 0, cost_usd: float = 0.0) -> dict:
        data = self.read()
        data["calls"] = int(data.get("calls", 0)) + 1
        data["tokens_in"] = int(data.get("tokens_in", 0)) + int(tokens_in or 0)
        data["tokens_out"] = int(data.get("tokens_out", 0)) + int(tokens_out or 0)
        data["cost_usd"] = round(float(data.get("cost_usd", 0.0)) + float(cost_usd or 0.0), 6)
        try:
            _write_json(self._path(), data)
        except OSError as error:
            logger.warning("Gagal mencatat pemakaian narasi: %s", error)
        return data


def estimate_cost(rules, tokens_in: int, tokens_out: int) -> float:
    """Perkiraan biaya dari harga per juta token yang dikonfigurasi operator."""
    price_in = rules.number("cost.price_input_per_mtok", 0.0)
    price_out = rules.number("cost.price_output_per_mtok", 0.0)
    return round(tokens_in / 1_000_000 * price_in + tokens_out / 1_000_000 * price_out, 6)
