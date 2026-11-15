import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.market import router as market_router
from app.api.research_dashboard import router as research_router
from app.api.scanner import router as scanner_router
from app.api.watchlist import router as watchlist_router
from app.api.watchlist_search import router as watchlist_search_router
from app.core.config import Settings
from app.market_data.hub import MarketHub
from app.market_data.service import stream_market_data


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    hub = MarketHub(feed=settings.market_data_feed)
    hub.select_watchlist([])
    application.state.market_hub = hub
    task: asyncio.Task[None] | None = None

    if settings.market_data_enabled:
        task = asyncio.create_task(stream_market_data(hub, settings))

    try:
        yield
    finally:
        if task is not None:
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task


app = FastAPI(
    title="StockTradingWeb API",
    description="Financial market analysis and portfolio tracking API",
    version="0.1.0",
    lifespan=lifespan,
)

app.include_router(market_router)
app.include_router(research_router)
app.include_router(scanner_router)
app.include_router(watchlist_router)
app.include_router(watchlist_search_router)


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
