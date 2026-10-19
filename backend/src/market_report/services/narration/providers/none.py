"""Provider kosong: dipakai bila LLM/search belum dikonfigurasi.

Provider ini selalu `available() == False`, sehingga engine langsung memakai
narasi deterministik tanpa memanggil jaringan. Ini kondisi normal saat
pengembangan (keputusan pengguna 16 Okt 2026).
"""

from __future__ import annotations

from typing import Sequence

from market_report.services.narration.errors import ProviderUnavailableError
from market_report.services.narration.providers.base import LLMResponse, RawSearchResult


class NullLLMProvider:
    name = "none"
    model = ""

    def __init__(self, reason: str = "Provider LLM belum dikonfigurasi."):
        self.reason = reason

    def available(self) -> bool:
        return False

    def generate(self, *, system: str, user: str, schema: dict | None = None,
                 max_tokens: int = 700, temperature: float = 0.2,
                 json_mode: bool = True) -> LLMResponse:
        raise ProviderUnavailableError(self.reason)


class NullSearchProvider:
    name = "none"

    def available(self) -> bool:
        return False

    def discover(self, *, topics: Sequence[str], since: str, max_items: int,
                 queries: Sequence[str] = ()) -> list[RawSearchResult]:
        return []
