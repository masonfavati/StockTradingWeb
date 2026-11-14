import asyncio
import json
from collections.abc import AsyncIterator
from typing import Any, cast

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.market_data.state import MarketState

router = APIRouter(prefix="/api/market", tags=["Market Data"])


def get_market_state(request: Request) -> MarketState:
    return cast(MarketState, request.app.state.market_state)


@router.get("/status")
def market_status(request: Request) -> dict[str, Any]:
    return get_market_state(request).snapshot()


@router.get("/events")
async def market_events(request: Request) -> StreamingResponse:
    async def generate() -> AsyncIterator[str]:
        while not await request.is_disconnected():
            snapshot = get_market_state(request).snapshot()
            yield f"data: {json.dumps(snapshot)}\n\n"
            await asyncio.sleep(1)

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )
