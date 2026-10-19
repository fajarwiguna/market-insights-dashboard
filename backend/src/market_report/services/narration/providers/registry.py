"""Pemilihan provider dari environment (satu titik ganti, blueprint bagian 18)."""

from __future__ import annotations

import logging
import os
from pathlib import Path

from market_report.services.narration.providers.base import LLMProvider, SearchProvider
from market_report.services.narration.providers.none import NullLLMProvider, NullSearchProvider
from market_report.services.narration.providers.openai_compatible import (
    OpenAICompatibleProvider,
    from_environment as llm_from_environment,
)

logger = logging.getLogger(__name__)

_OPENAI_COMPATIBLE_NAMES = {"openai-compatible", "openai_compatible", "openai", "compatible", "gateway"}


def narrative_enabled() -> bool:
    """Fitur dinonaktifkan secara default (default aman)."""
    from market_report.config import load_environment

    try:
        load_environment()
    except Exception:  # pragma: no cover - .env opsional saat pengujian
        pass
    return os.environ.get("LLM_NARRATIVE_ENABLED", "").strip().lower() in {"1", "true", "yes", "on"}


def llm_provider(*, override: LLMProvider | None = None, post=None) -> LLMProvider:
    """Bangun provider LLM sesuai `LLM_PROVIDER`."""
    if override is not None:
        return override
    from market_report.config import load_environment

    try:
        load_environment()
    except Exception:  # pragma: no cover
        pass
    name = os.environ.get("LLM_PROVIDER", "").strip().lower()
    if not name or name == "none":
        return NullLLMProvider("LLM_PROVIDER belum diarahkan ke provider mana pun.")
    if name in _OPENAI_COMPATIBLE_NAMES:
        provider = llm_from_environment(post)
        if not provider.available():
            # Key/model boleh kosong saat pengembangan: jangan gagal, cukup fallback.
            missing = [key for key, value in (("LLM_BASE_URL", provider.base_url), ("LLM_API_KEY", provider.api_key),
                                              ("LLM_MODEL", provider.model)) if not value]
            logger.info("Provider LLM belum lengkap (%s); narasi memakai fallback deterministik.",
                        ", ".join(missing) or "konfigurasi")
            return NullLLMProvider(f"Konfigurasi provider belum lengkap: {', '.join(missing)}")
        return provider
    logger.warning("LLM_PROVIDER '%s' belum didukung; narasi memakai fallback.", name)
    return NullLLMProvider(f"Provider LLM '{name}' belum didukung.")


def _registry_path(configured: str) -> Path:
    from market_report.config import project_root

    root = project_root()
    candidate = Path(configured or "backend/config/llm_sources.json")
    return candidate if candidate.is_absolute() else root / candidate


def search_provider(*, override: SearchProvider | None = None, fetcher=None,
                    registry_path: str = "", max_articles_per_source: int = 4) -> SearchProvider:
    """Bangun provider bukti sesuai `SEARCH_PROVIDER`."""
    if override is not None:
        return override
    from market_report.config import load_environment

    try:
        load_environment()
    except Exception:  # pragma: no cover
        pass
    name = os.environ.get("SEARCH_PROVIDER", "seeded").strip().lower()
    if name in {"none", "off", "disabled"}:
        return NullSearchProvider()
    if name == "seeded":
        from market_report.services.narration.providers.search_seeded import (
            SeededSearchProvider,
            load_registry,
        )

        path = _registry_path(registry_path or "backend/config/llm_sources.json")
        registry = load_registry(path)
        if not registry:
            return NullSearchProvider()
        limits = registry.get("rules") or {}
        return SeededSearchProvider(
            registry,
            fetcher=fetcher,
            timeout=float(limits.get("fetch_timeout_seconds") or 20),
            max_bytes=int(limits.get("max_bytes_per_page") or 2_000_000),
            max_articles_per_source=max_articles_per_source,
        )
    logger.warning("SEARCH_PROVIDER '%s' belum didukung; konteks eksternal dilewati.", name)
    return NullSearchProvider()
