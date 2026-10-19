"""Provider palsu untuk pengujian: tanpa jaringan, tanpa kredensial."""

from __future__ import annotations

from typing import Sequence

from market_report.services.narration.providers.base import LLMResponse, RawSearchResult


class FakeLLMProvider:
    """Kembalikan jawaban berskrip; catat setiap panggilan untuk diperiksa test."""

    name = "fake"

    def __init__(self, responses: Sequence[str] | None = None, *, model: str = "fake-model",
                 error: Exception | None = None):
        self.responses = list(responses or [])
        self.model = model
        self.error = error
        self.calls: list[dict] = []

    def available(self) -> bool:
        return True

    def generate(self, *, system: str, user: str, schema: dict | None = None,
                 max_tokens: int = 700, temperature: float = 0.2,
                 json_mode: bool = True) -> LLMResponse:
        self.calls.append({"system": system, "user": user, "schema": schema,
                           "max_tokens": max_tokens, "temperature": temperature,
                           "json_mode": json_mode})
        if self.error is not None:
            raise self.error
        text = self.responses.pop(0) if self.responses else "{}"
        return LLMResponse(text=text, tokens_in=100, tokens_out=80, model=self.model, latency_ms=5)


class FakeSearchProvider:
    name = "fake-search"

    def __init__(self, results: Sequence[RawSearchResult] | None = None,
                 *, error: Exception | None = None):
        self.results = list(results or [])
        self.error = error
        self.calls: list[dict] = []

    def available(self) -> bool:
        return True

    def discover(self, *, topics: Sequence[str], since: str, max_items: int,
                 queries: Sequence[str] = ()) -> list[RawSearchResult]:
        self.calls.append({"topics": list(topics), "since": since, "max_items": max_items,
                           "queries": list(queries)})
        if self.error is not None:
            raise self.error
        if not topics:
            return self.results[:max_items]
        wanted = {topic.lower() for topic in topics}
        return [row for row in self.results
                if not row.topics or wanted & {topic.lower() for topic in row.topics}][:max_items]
