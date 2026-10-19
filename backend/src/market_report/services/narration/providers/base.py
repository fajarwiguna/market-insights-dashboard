"""Interface provider: satu-satunya ketergantungan engine pada vendor.

Business logic tidak boleh mengimpor SDK vendor. Implementasi konkret cukup
memenuhi protokol di bawah ini, sehingga provider dapat diganti lewat
environment (`LLM_PROVIDER`, `SEARCH_PROVIDER`) tanpa mengubah engine.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import NamedTuple, Protocol, Sequence, runtime_checkable


class LLMResponse(NamedTuple):
    text: str
    tokens_in: int
    tokens_out: int
    model: str
    latency_ms: int


@dataclass(frozen=True)
class RawSearchResult:
    """Hasil mentah pencarian; belum tersanitasi, belum berbentuk evidence."""

    title: str
    url: str
    source: str
    published_at: str = ""
    summary: str = ""
    text: str = ""
    source_tier: str = "secondary"
    topics: tuple[str, ...] = ()
    publisher: str = ""
    event_at: str = ""
    query: str = ""
    meta: dict = field(default_factory=dict)


@runtime_checkable
class LLMProvider(Protocol):
    name: str
    model: str

    def available(self) -> bool:
        """True bila provider siap dipakai (konfigurasi lengkap dan sehat)."""

    def generate(self, *, system: str, user: str, schema: dict | None = None,
                 max_tokens: int = 700, temperature: float = 0.2,
                 json_mode: bool = True) -> LLMResponse:
        ...


@runtime_checkable
class SearchProvider(Protocol):
    name: str

    def available(self) -> bool:
        ...

    def discover(self, *, topics: Sequence[str], since: str, max_items: int,
                 queries: Sequence[str] = ()) -> list[RawSearchResult]:
        """Cari bukti untuk topik yang dibutuhkan pada rentang sejak `since`.

        `queries` adalah kueri pencarian dinamis yang diturunkan dari sinyal
        pasar sesi ini (lihat `services/narration/signals.py`). Provider yang
        tidak mendukung pencarian bebas boleh memakainya untuk memeringkat.
        """
