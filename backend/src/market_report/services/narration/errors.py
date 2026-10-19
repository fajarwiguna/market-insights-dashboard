"""Taksonomi kegagalan Narrative Engine (blueprint bagian 14).

Semua kegagalan di sini berarti "pakai fallback", bukan "hancurkan halaman".
"""

from __future__ import annotations


class NarrativeError(Exception):
    """Dasar seluruh kegagalan narasi."""

    code = "narrative_error"


class RulesUnavailableError(NarrativeError):
    code = "rules_unavailable"


class ContextUnavailableError(NarrativeError):
    code = "context_unavailable"


class ProviderUnavailableError(NarrativeError):
    code = "provider_unavailable"


class ProviderTimeoutError(ProviderUnavailableError):
    code = "provider_timeout"


class InvalidOutputError(NarrativeError):
    code = "invalid_output"


class ValidationRejectedError(NarrativeError):
    code = "validation_rejected"

    def __init__(self, message: str, issues: list | None = None):
        super().__init__(message)
        self.issues = issues or []


class BudgetExhaustedError(NarrativeError):
    code = "budget_exhausted"


class SearchUnavailableError(NarrativeError):
    """Kegagalan web search tidak fatal: narasi lanjut tanpa konteks eksternal."""

    code = "search_unavailable"


def classify(error: Exception) -> str:
    """Kode ringkas untuk log dan audit."""
    return getattr(error, "code", error.__class__.__name__)
