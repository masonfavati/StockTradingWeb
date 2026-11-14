import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI

from app.api.market import router as market_router
from app.core.config import Settings
from app.market_data.service import stream_market_data
from app.market_data.state import MarketState


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    settings = Settings()
    state = MarketState(
        feed=settings.market_data_feed,
        symbol=settings.market_data_symbol.upper(),
    )

    application.state.market_state = state
    task: asyncio.Task[None] | None = None

    if settings.market_data_enabled:
        if state.feed == "test" and state.symbol != "FAKEPACA":
            state.connection_status = "configuration_error"
            state.error = "Test feed requires FAKEPACA"
        elif state.feed == "iex" and state.symbol == "FAKEPACA":
            state.connection_status = "configuration_error"
            state.error = "IEX feed requires a real stock symbol"
        else:
            task = asyncio.create_task(
                stream_market_data(state, settings)
            )

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


@app.get("/api/health", tags=["Health"])
def health_check() -> dict[str, str]:
    return {"status": "ok"}
