"""Schema respons API; bagian data tetap kompatibel dengan laporan Streamlit."""

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ReportResponse(BaseModel):
    """Metadata stabil dengan data laporan lama dipertahankan apa adanya."""

    model_config = ConfigDict(extra="allow")

    report_id: str | None = None
    schema_version: int = 1
    report_date: str | None = None
    report_date_iso: str | None = None
    generated_at: str | None = None
    published_at: str | None = None
    is_demo: bool = False
    fx: dict[str, dict[str, Any]] = Field(default_factory=dict)
    indices: dict[str, dict[str, Any]] = Field(default_factory=dict)
    yields: dict[str, dict[str, Any]] = Field(default_factory=dict)
    commodities: dict[str, dict[str, Any]] = Field(default_factory=dict)


class HistoryPoint(BaseModel):
    dates: str
    close: float


class InstrumentHistoryResponse(BaseModel):
    instrument_id: str
    points: list[HistoryPoint]


class LiveQuote(BaseModel):
    status: str
    last: float | None = None
    prev: float | None = None
    change_pct: float | None = None
    dates: str | None = None
    source: str | None = None


class LiveMarketResponse(BaseModel):
    fetched_at: str | None = None
    status: str
    quotes: dict[str, LiveQuote]
