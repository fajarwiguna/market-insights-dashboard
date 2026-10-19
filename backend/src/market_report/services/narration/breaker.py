"""Circuit breaker sederhana untuk provider LLM dan sumber bukti.

Setelah beberapa kegagalan berturut-turut, pemanggilan provider dihentikan
sementara supaya biaya dan waktu tidak terbuang saat layanan sedang bermasalah.
Status disimpan di runtime agar bertahan antarproses.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

from market_report.services.narration.cache import narrative_directory

logger = logging.getLogger(__name__)

DEFAULT_THRESHOLD = 3
DEFAULT_OPEN_MINUTES = 15


class CircuitBreaker:
    def __init__(self, name: str, *, threshold: int = DEFAULT_THRESHOLD,
                 open_minutes: int = DEFAULT_OPEN_MINUTES, directory: Path | None = None):
        self.name = name
        self.threshold = threshold
        self.open_minutes = open_minutes
        self.directory = Path(directory) if directory else narrative_directory() / "breaker"

    @property
    def _path(self) -> Path:
        return self.directory / f"{self.name}.json"

    def _read(self) -> dict:
        try:
            return json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"failures": 0, "opened_until": ""}

    def _write(self, payload: dict) -> None:
        try:
            self.directory.mkdir(parents=True, exist_ok=True)
            handle = tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=self.directory,
                                                 prefix=self.name, suffix=".tmp", delete=False)
            try:
                json.dump(payload, handle, ensure_ascii=False)
                handle.flush()
                os.fsync(handle.fileno())
            finally:
                handle.close()
            os.replace(handle.name, self._path)
        except OSError as error:
            logger.warning("Gagal menyimpan status breaker %s: %s", self.name, error)

    def is_open(self) -> bool:
        state = self._read()
        opened_until = state.get("opened_until") or ""
        if not opened_until:
            return False
        try:
            until = datetime.fromisoformat(str(opened_until))
        except ValueError:
            return False
        if until.tzinfo is None:
            until = until.replace(tzinfo=timezone.utc)
        return datetime.now(timezone.utc) < until

    def record_failure(self) -> None:
        state = self._read()
        failures = int(state.get("failures", 0)) + 1
        payload = {"failures": failures, "opened_until": state.get("opened_until") or ""}
        if failures >= self.threshold:
            payload["opened_until"] = (datetime.now(timezone.utc)
                                       + timedelta(minutes=self.open_minutes)).isoformat(timespec="seconds")
            payload["failures"] = 0
            logger.warning("Breaker %s dibuka selama %s menit setelah %s kegagalan.",
                           self.name, self.open_minutes, failures)
        self._write(payload)

    def record_success(self) -> None:
        self._write({"failures": 0, "opened_until": ""})

    def reset(self) -> None:
        self._write({"failures": 0, "opened_until": ""})
