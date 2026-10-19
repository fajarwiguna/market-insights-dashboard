"""Implementasi provider LLM dan sumber bukti.

Provider konkret tidak boleh diimpor langsung oleh engine selain melalui
`registry.py`, supaya penggantian vendor hanya menyentuh satu tempat.
"""

from market_report.services.narration.providers.base import (
    LLMProvider,
    LLMResponse,
    RawSearchResult,
    SearchProvider,
)
from market_report.services.narration.providers.fake import FakeLLMProvider, FakeSearchProvider
from market_report.services.narration.providers.none import NullLLMProvider, NullSearchProvider
from market_report.services.narration.providers.registry import (
    llm_provider,
    narrative_enabled,
    search_provider,
)

__all__ = [
    "LLMProvider", "LLMResponse", "RawSearchResult", "SearchProvider",
    "FakeLLMProvider", "FakeSearchProvider", "NullLLMProvider", "NullSearchProvider",
    "llm_provider", "search_provider", "narrative_enabled",
]
