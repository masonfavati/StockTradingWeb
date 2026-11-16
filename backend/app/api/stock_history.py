"""Read-only, bounded historical chart API independent of opportunity scans."""

import time
from collections import OrderedDict, deque
from datetime import UTC, datetime
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, HTTPException

from app.analysis.stock_history_chart import (
    ChartHistoryError,
    build_stock_history,
    completed_cutoff,
    validate_symbol,
)
from app.core.config import Settings
from app.market_data.history_client import AlpacaHistoryClient, HistoricalDataError

router = APIRouter(prefix="/api/research", tags=["Historical stock chart"])
_TTL_SECONDS = 600
_MAX_CACHE_ENTRIES = 64
_MAX_FETCHES_PER_MINUTE = 12
_cache: OrderedDict[tuple[str, str, bool, str], tuple[float, dict[str, Any]]] = OrderedDict()
_recent_fetches: deque[float] = deque()
_lock = Lock()


@router.get("/stock-history/{symbol}")
def stock_history(
    symbol: str, period: Literal["1m", "3m", "1y", "5y"] = "1y",
    compare_spy: bool = False,
) -> dict[str, Any]:
    """One ticker, up to five years; no scanner, journal, or data import required."""
    try:
        ticker = validate_symbol(symbol)
    except ChartHistoryError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    now = datetime.now(UTC)
    key = (ticker, period, compare_spy, completed_cutoff(now).date().isoformat())
    clock = time.monotonic()
    with _lock:
        cached = _cache.get(key)
        if cached is not None and clock - cached[0] < _TTL_SECONDS:
            _cache.move_to_end(key)
            return cached[1]
        _cache.pop(key, None)
        while _recent_fetches and clock - _recent_fetches[0] >= 60:
            _recent_fetches.popleft()
        if len(_recent_fetches) >= _MAX_FETCHES_PER_MINUTE:
            raise HTTPException(
                status_code=429,
                detail="Historical chart request limit reached. Retry in a minute.",
            )
        _recent_fetches.append(clock)
    try:
        result = build_stock_history(
            AlpacaHistoryClient(Settings()), symbol=ticker, period=period,
            compare_spy=compare_spy, now=now,
        )
    except (ChartHistoryError, HistoricalDataError, OSError, ValueError, ArithmeticError) as exc:
        # No fabricated bars or leaking credentials and provider details.
        raise HTTPException(
            status_code=503,
            detail="Historical market data is unavailable or invalid. No chart was published.",
        ) from exc
    with _lock:
        _cache[key] = (clock, result)
        _cache.move_to_end(key)
        while len(_cache) > _MAX_CACHE_ENTRIES:
            _cache.popitem(last=False)
    return result
