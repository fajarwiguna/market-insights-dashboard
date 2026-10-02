"""Endpoint harga live dengan cache singkat per proses API."""

from fastapi import APIRouter, Depends

from market_report.api.dependencies import require_read_access
from market_report.api.schemas import LiveMarketResponse
from market_report.services.live_service import fetch_live_prices_cached


router = APIRouter(prefix="/market", tags=["market"], dependencies=[Depends(require_read_access)])


@router.get("/live", response_model=LiveMarketResponse, summary="Baca harga market live")
def read_live_market() -> dict:
    payload = fetch_live_prices_cached()
    quotes = {}
    for key, value in payload.items():
        if key.startswith("_") or not isinstance(value, dict):
            continue
        quote = {
            "status": "unavailable" if value.get("error") or value.get("last") is None else "available",
            "last": value.get("last"),
            "prev": value.get("prev"),
            "change_pct": value.get("change_pct"),
            "dates": value.get("date"),
            "source": value.get("source"),
        }
        quotes[key] = quote

    available_count = sum(quote["status"] == "available" for quote in quotes.values())
    if not available_count:
        status = "unavailable"
    elif available_count < len(quotes):
        status = "partial"
    else:
        status = "available"
    return {"fetched_at": payload.get("_fetched_at"), "status": status, "quotes": quotes}
