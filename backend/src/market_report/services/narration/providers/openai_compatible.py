"""Provider LLM untuk endpoint OpenAI-compatible (mis. gateway internal).

Memakai `requests` yang sudah menjadi dependensi proyek, jadi tidak ada SDK
vendor baru. Provider ini juga dipakai oleh gateway OpenAI-compatible lain.

Catatan konfigurasi: bila `LLM_BASE_URL` diisi tanpa segmen versi
(mis. `https://opus.abhibots.com`), jalur yang dipakai adalah
`{base}/v1/chat/completions`. Gunakan `LLM_CHAT_PATH` untuk menimpanya.
"""

from __future__ import annotations

import logging
import os
import time
from typing import Callable

from market_report.services.narration.errors import (
    InvalidOutputError,
    ProviderTimeoutError,
    ProviderUnavailableError,
)
from market_report.services.narration.providers.base import LLMResponse

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 45.0


class OpenAICompatibleProvider:
    name = "openai-compatible"

    def __init__(self, *, base_url: str, api_key: str, model: str, timeout: float = DEFAULT_TIMEOUT_SECONDS,
                 chat_path: str = "", post: Callable[..., object] | None = None,
                 json_mode: bool = True):
        self.base_url = (base_url or "").strip().rstrip("/")
        self.api_key = (api_key or "").strip()
        self.model = (model or "").strip()
        self.timeout = timeout
        self.chat_path = (chat_path or "").strip()
        self.json_mode = json_mode
        self._post = post
        self._json_mode_rejected = False

    # ── kesiapan ────────────────────────────────────────────────

    def available(self) -> bool:
        """Provider, model, dan key harus lengkap; kalau tidak, engine memakai fallback."""
        return bool(self.base_url and self.api_key and self.model)

    def endpoint(self) -> str:
        if self.chat_path:
            return self.chat_path if self.chat_path.startswith("http") else f"{self.base_url}{self.chat_path}"
        if not self.base_url:
            return ""
        if self.base_url.endswith("/chat/completions"):
            return self.base_url
        if "/v1" in self.base_url:
            return f"{self.base_url}/chat/completions"
        return f"{self.base_url}/v1/chat/completions"

    def _post_json(self, url: str, payload: dict, headers: dict, timeout: float):
        if self._post is not None:
            return self._post(url, payload, headers, timeout)
        import requests  # diimpor lokal agar modul tetap ringan saat provider tidak dipakai

        return requests.post(url, json=payload, headers=headers, timeout=timeout)

    # ── panggilan ───────────────────────────────────────────────

    def generate(self, *, system: str, user: str, schema: dict | None = None,
                 max_tokens: int = 700, temperature: float = 0.2,
                 json_mode: bool = True) -> LLMResponse:
        if not self.available():
            raise ProviderUnavailableError("Provider LLM belum dikonfigurasi lengkap.")

        payload: dict[str, object] = {
            "model": self.model,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode and self.json_mode and not self._json_mode_rejected:
            payload["response_format"] = {"type": "json_object"}
        headers = {"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"}

        started = time.monotonic()
        response = self._send(payload, headers)
        if response is None:
            self._json_mode_rejected = True
            payload.pop("response_format", None)
            logger.warning("Endpoint menolak mode JSON; mencoba ulang tanpa response_format.")
            response = self._send(payload, headers)
        latency_ms = int((time.monotonic() - started) * 1000)

        try:
            body = response.json()
        except Exception as error:
            raise InvalidOutputError("Respons provider bukan JSON.") from error
        if not isinstance(body, dict):
            raise InvalidOutputError("Bentuk respons provider tidak dikenali.")
        choices = body.get("choices") or []
        if not choices:
            raise InvalidOutputError("Provider tidak mengembalikan pilihan jawaban.")
        message = choices[0].get("message") or {}
        text = message.get("content")
        if not isinstance(text, str) or not text.strip():
            raise InvalidOutputError("Provider mengembalikan narasi kosong.")
        usage = body.get("usage") or {}
        return LLMResponse(
            text=text,
            tokens_in=int(usage.get("prompt_tokens") or 0),
            tokens_out=int(usage.get("completion_tokens") or 0),
            model=str(body.get("model") or self.model),
            latency_ms=latency_ms,
        )

    def _send(self, payload: dict, headers: dict):
        """Kirim permintaan; kembalikan None bila hanya `response_format` yang ditolak."""
        url = self.endpoint()
        try:
            response = self._post_json(url, payload, headers, self.timeout)
        except Exception as error:
            name = error.__class__.__name__.lower()
            if "timeout" in name:
                raise ProviderTimeoutError("Panggilan LLM melewati batas waktu.") from error
            raise ProviderUnavailableError(f"Panggilan LLM gagal: {name}") from error

        status = getattr(response, "status_code", 0)
        if status == 400 and "response_format" in payload:
            detail = _error_detail(response)
            if "response_format" in detail or "json" in detail:
                return None
            raise InvalidOutputError(f"Provider menolak permintaan: {detail[:160]}")
        if status in (401, 403, 404) or status == 429 or status >= 500:
            # 401/403/404 = kredensial/izin/endpoint bermasalah, bukan keluaran buruk;
            # 429/5xx = batas laju atau gangguan provider. Semua berarti "pakai fallback".
            detail = _error_detail(response)
            message = f"Provider sedang tidak tersedia (HTTP {status})."
            if detail:
                message = f"Provider sedang tidak tersedia (HTTP {status}): {detail}"
            error = ProviderUnavailableError(message)
            error.retry_after = _retry_after_seconds(response)
            raise error
        if status >= 400:
            raise InvalidOutputError(f"Permintaan ditolak provider (HTTP {status}): "
                                     f"{_error_detail(response)[:160]}")
        return response


def _error_detail(response) -> str:
    """Ambil pesan error dari body JSON provider (mis. 'Daily token limit exceeded')."""
    detail = ""
    try:
        body = response.json()
    except Exception:
        body = None
    if isinstance(body, dict):
        error = body.get("error")
        if isinstance(error, dict):
            detail = str(error.get("message") or error.get("code") or "")
        elif isinstance(error, str):
            detail = error
    if not detail:
        detail = _safe_text(response)
    return " ".join((detail or "").split())[:200]


def _retry_after_seconds(response) -> float | None:
    """Baca header Retry-After (dalam detik) bila tersedia dan berupa angka."""
    headers = getattr(response, "headers", None)
    try:
        raw = headers.get("Retry-After") if headers is not None else None
    except Exception:
        raw = None
    try:
        return float(raw) if raw is not None else None
    except (TypeError, ValueError):
        return None


def _safe_text(response) -> str:
    try:
        return str(response.text or "")
    except Exception:
        return ""


def from_environment(post: Callable[..., object] | None = None) -> OpenAICompatibleProvider:
    """Bangun provider dari environment; kosong berarti provider tidak tersedia."""
    from market_report.config import load_environment

    try:
        load_environment()
    except Exception:  # pragma: no cover - .env bersifat opsional saat pengujian
        pass
    timeout = os.environ.get("LLM_TIMEOUT_SECONDS", "").strip()
    try:
        timeout_value = float(timeout) if timeout else DEFAULT_TIMEOUT_SECONDS
    except ValueError:
        timeout_value = DEFAULT_TIMEOUT_SECONDS
    return OpenAICompatibleProvider(
        base_url=os.environ.get("LLM_BASE_URL", ""),
        api_key=os.environ.get("LLM_API_KEY", ""),
        model=os.environ.get("LLM_MODEL", ""),
        timeout=timeout_value,
        chat_path=os.environ.get("LLM_CHAT_PATH", ""),
        post=post,
        json_mode=os.environ.get("LLM_JSON_MODE", "true").strip().lower() != "false",
    )
