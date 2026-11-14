import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.market_data.hub import MarketHub

router = APIRouter(prefix="/api/market", tags=["Market Data"])


def get_market_hub(request: Request) -> MarketHub:
    return cast(MarketHub, request.app.state.market_hub)


@router.get("/status")
def market_status(request: Request) -> dict[str, Any]:
    return get_market_hub(request).primary_snapshot()


@router.get("/monitored")
def monitored_stocks(request: Request) -> dict[str, Any]:
    return get_market_hub(request).list_snapshot()


@router.get("/monitored/events")
async def monitored_events(request: Request) -> StreamingResponse:
    """One browser connection; no additional Alpaca subscription per tab."""

    async def generate() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            yield f"data: {json.dumps(get_market_hub(request).list_snapshot())}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/events")
async def market_events(request: Request) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            snapshot = get_market_hub(request).primary_snapshot()
            yield f"data: {json.dumps(snapshot)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )
