"""Bounded, independently fetched daily stock history for visual inspection.

This is a retrospective display, not scanner input, point-in-time model data,
current trade prices, or a prediction of the future.  No scans are needed.
"""

import math
import re
from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Any, Literal, Protocol
from zoneinfo import ZoneInfo

from app.analysis.historical_insights import describe_price_history
from app.market_data.history_client import DailyBar, HistoryAdjustment, HistoryFeed

Period = Literal["1m", "3m", "1y", "5y"]
NY = ZoneInfo("America/New_York")
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")
_PERIOD_DAYS: dict[Period, int] = {"1m": 40, "3m": 110, "1y": 390, "5y": 1850}
_EARLIEST = date(2016, 1, 1)  # Alpaca's stated stock-data history limit
_MAX_PAGES = 6
_MAX_BARS = 1700
_MAX_TOTAL_BARS = 3400


class ChartHistoryError(ValueError):
    """Unusable or inconsistent source history; no partial chart is published."""


class HistoricalBars(Protocol):
    def pages(
        self, symbols: Sequence[str], *, start: date, end: datetime,
        feed: HistoryFeed, adjustment: HistoryAdjustment, page_limit: int,
    ) -> Iterator[list[DailyBar]]: ...


def validate_symbol(value: str) -> str:
    normalized = value.strip().upper()
    if _SYMBOL.fullmatch(normalized) is None:
        raise ChartHistoryError("Enter one valid US stock ticker, such as AAPL.")
    return normalized


def completed_cutoff(now: datetime) -> datetime:
    """Conservatively finish at 23:00 NY of the *previous* calendar day.

    Keeps the free historical SIP endpoint outside the recent-data entitlement
    window, and excludes today's incomplete daily candle.
    """
    if now.tzinfo is None:
        raise ValueError("A timezone-aware current time is required.")
    previous_ny_day = now.astimezone(NY).date() - timedelta(days=1)
    return datetime.combine(previous_ny_day, time(23), tzinfo=NY).astimezone(UTC)


def _safe_price(value: Decimal) -> float:
    try:
        result = float(value)
    except (ValueError, OverflowError) as exc:
        raise ChartHistoryError("Historical prices are outside supported bounds.") from exc
    if not math.isfinite(result) or result < 0.00000001 or result > 1_000_000_000:
        raise ChartHistoryError("Historical prices are outside supported bounds.")
    return result


def build_stock_history(
    provider: HistoricalBars, *, symbol: str, period: Period,
    compare_spy: bool, now: datetime,
) -> dict[str, Any]:
    """Fetch historical bars on-demand, independent of saved scanner checkpoints.

    The benchmark is aligned by **actual session dates**, never filled with
    guessed observations. The current forecast model predicts relative SPY
    outperformance, not future share prices; no price path is fabricated.
    """
    symbol = validate_symbol(symbol)
    if period not in _PERIOD_DAYS:
        raise ChartHistoryError("Unsupported history period.")
    cutoff = completed_cutoff(now)
    latest_possible_day = cutoff.astimezone(NY).date()
    start = max(_EARLIEST, latest_possible_day - timedelta(days=_PERIOD_DAYS[period]))
    benchmark_requested = compare_spy and symbol != "SPY"
    symbols = [symbol, "SPY"] if benchmark_requested else [symbol]
    prices: dict[str, dict[date, float]] = {item: {} for item in symbols}
    points = 0
    for pages, rows in enumerate(provider.pages(
        symbols, start=start, end=cutoff, feed="sip", adjustment="all", page_limit=1000,
    ), start=1):
        if pages > _MAX_PAGES:
            raise ChartHistoryError("History exceeds the bounded chart request capacity.")
        for item in rows:
            points += 1
            if points > _MAX_TOTAL_BARS or item.symbol not in prices:
                raise ChartHistoryError("Historical provider returned excess or unexpected rows.")
            day = item.session_date
            if not (start <= day <= latest_possible_day) or day >= now.astimezone(NY).date():
                raise ChartHistoryError("Historical provider returned a future or incomplete session.")
            if day in prices[item.symbol]:
                raise ChartHistoryError("Duplicate historical sessions cannot be displayed.")
            if len(prices[item.symbol]) >= _MAX_BARS:
                raise ChartHistoryError("History exceeds the supported chart length.")
            prices[item.symbol][day] = _safe_price(item.close_price)

    stock = prices[symbol]
    available_days = sorted(stock)
    spy = prices.get("SPY", {})
    shared = [day for day in available_days if day in spy]
    usable_benchmark = benchmark_requested and len(shared) >= 2
    # In comparison mode, show ONLY matched sessions: both indexed lines start
    # at exactly 100 and no missing benchmark prices are fabricated.
    days = shared if usable_benchmark else available_days
    anchor = days[0] if days else None
    anchor_price = stock[anchor] if anchor is not None else None
    anchor_spy = spy[anchor] if usable_benchmark and anchor is not None else None
    chart = [
        {
            "session_date": day.isoformat(),
            "adjusted_close_usd": round(stock[day], 8),
            "normalized_index": round(stock[day] / anchor_price * 100, 4)
            if anchor_price is not None else None,
        }
        for day in days
    ]
    benchmark = [
        {"session_date": day.isoformat(), "normalized_index": round(spy[day] / anchor_spy * 100, 4)}
        for day in shared
    ] if usable_benchmark and anchor_spy is not None else []
    first = stock[days[0]] if days else None
    last = stock[days[-1]] if days else None
    change_pct = round((last / first - 1) * 100, 2) if first is not None and last is not None else None
    warning: str | None = None
    if not days:
        warning = "No historical bars were returned for this ticker and date range."
    elif benchmark_requested and not usable_benchmark:
        warning = "There are not enough identical stock and SPY trading sessions for comparison."
    elif usable_benchmark and len(days) < len(available_days):
        warning = "Comparison displays only dates with real bars for both the stock and SPY."
    elif (latest_possible_day - days[-1]).days > 7:
        warning = "The latest available historical bar is more than seven calendar days old."
    return {
        "version": "independent-stock-history-v1",
        "symbol": symbol,
        "period": period,
        "provider": "alpaca",
        "feed": "sip",
        "adjustment": "all",
        "timeframe": "1Day",
        "fetched_at_utc": now.astimezone(UTC).isoformat(),
        "provider_cutoff_utc": cutoff.isoformat(),
        "first_session": days[0].isoformat() if days else None,
        "last_session": days[-1].isoformat() if days else None,
        "session_count": len(days),
        "first_adjusted_close_usd": round(first, 8) if first is not None else None,
        "last_adjusted_close_usd": round(last, 8) if last is not None else None,
        "period_change_pct": change_pct,
        "historical_insights": describe_price_history(
            [(day, stock[day]) for day in days],
            spy_observations=[(day, spy[day]) for day in shared] if usable_benchmark else [],
        ),
        "benchmark_requested": benchmark_requested,
        "benchmark_available": usable_benchmark,
        "benchmark_anchor_session": anchor.isoformat() if usable_benchmark and anchor else None,
        "bars": chart,
        "spy_benchmark": benchmark,
        "warning": warning,
        "price_forecast": None,
        "forecast_status": "no_validated_price_forecast",
        "forecast_explanation": (
            "The prospective model currently estimates conditional chances of outperforming SPY "
            "over 20 sessions. That is not a dollar-price or price-path forecast, "
            "so the chart deliberately draws no future price line."
        ),
        "caveat": (
            "Historical daily SIP prices are adjusted using corporate actions known today "
            "(dividends, splits and spin-offs). They are not executable quotes, "
            "point-in-time prediction inputs, or guaranteed total returns. "
            "Ticker reuse and renames may affect long histories; no identity mapping is inferred."
        ),
    }
