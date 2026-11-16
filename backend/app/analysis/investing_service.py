"""Bounded independent five-year history retrieval for growth research."""

import math
from collections.abc import Iterator, Mapping, Sequence
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Protocol
from zoneinfo import ZoneInfo

from app.analysis.historical_growth import PricePoint, validate_history
from app.analysis.stock_history_chart import completed_cutoff, validate_symbol
from app.market_data.history_client import DailyBar, HistoryAdjustment, HistoryFeed

MAX_SYMBOLS = 12  # includes SPY
MAX_PAGES_PER_BATCH = 8
MAX_TOTAL_ROWS = 24_000
BATCH_SIZE = 6


class InvestingDataError(ValueError):
    """Research provider returned unusable, incomplete, or excessive data."""


class HistoryProvider(Protocol):
    def pages(
        self, symbols: Sequence[str], *, start: date, end: datetime,
        feed: HistoryFeed, adjustment: HistoryAdjustment, page_limit: int,
    ) -> Iterator[list[DailyBar]]: ...


def fetch_growth_histories(
    provider: HistoryProvider, symbols: Sequence[str], *, now: datetime,
    calendar_days: int = 1850, adjustment: HistoryAdjustment = "all",
) -> dict[str, list[PricePoint]]:
    if now.tzinfo is None:
        raise InvestingDataError("A timezone-aware calculation time is required.")
    unique = sorted({validate_symbol(symbol) for symbol in symbols})
    if not unique or len(unique) > MAX_SYMBOLS:
        raise InvestingDataError("Choose at most eleven stocks and the broad-market reference.")
    if not 400 <= calendar_days <= 1850:
        raise InvestingDataError("Unsupported historical period.")
    cutoff = completed_cutoff(now)
    latest_completed_ny = now.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)
    from_day = max(date(2016, 1, 1), latest_completed_ny - timedelta(days=calendar_days))
    grouped: dict[str, dict[date, float]] = {symbol: {} for symbol in unique}
    received = 0
    for offset in range(0, len(unique), BATCH_SIZE):
        batch = unique[offset : offset + BATCH_SIZE]
        for page, bars in enumerate(provider.pages(
            batch, start=from_day, end=cutoff, feed="sip", adjustment=adjustment, page_limit=10000,
        ), start=1):
            if page > MAX_PAGES_PER_BATCH:
                raise InvestingDataError("History download exceeded bounded pagination.")
            for bar in bars:
                received += 1
                if received > MAX_TOTAL_ROWS or bar.symbol not in grouped:
                    raise InvestingDataError("History download exceeded size or symbol limits.")
                if not from_day <= bar.session_date <= latest_completed_ny:
                    raise InvestingDataError("Provider returned dates outside the completed period.")
                history = grouped[bar.symbol]
                if bar.session_date in history:
                    raise InvestingDataError("Duplicate historical trading session.")
                try:
                    price = float(bar.close_price)
                except (ValueError, OverflowError) as exc:
                    raise InvestingDataError("Invalid adjusted historical price.") from exc
                history[bar.session_date] = price
    return {
        symbol: validate_history([PricePoint(day, close) for day, close in entries.items()])
        for symbol, entries in grouped.items()
    }


def _holding_value(raw: object) -> float:
    """Accept real recorded dollar values; never treat bad records as valid prices."""
    if isinstance(raw, bool) or not isinstance(raw, (str, int, float, Decimal)):
        raise InvestingDataError("Invalid recorded holding value.")
    try:
        amount = float(raw)
    except (ValueError, OverflowError) as exc:
        raise InvestingDataError("Invalid recorded holding value.") from exc
    if not math.isfinite(amount) or amount < 0:
        raise InvestingDataError("Invalid recorded holding value.")
    return amount


def price_review_alerts(
    holdings: Sequence[Mapping[str, object]], histories: Mapping[str, Sequence[PricePoint]],
    *, drop_threshold_pct: float = 12.0,
) -> list[dict[str, object]]:
    """Rule-based review alerts, NOT attempts to detect the market peak."""
    if not 5 <= drop_threshold_pct <= 50:
        raise InvestingDataError("Choose a review threshold between 5% and 50%.")
    rows: list[dict[str, object]] = []
    known_values = [
        _holding_value(value)
        for row in holdings
        if (value := row.get("estimated_value_usd")) is not None
    ]
    sum_values = sum(known_values)
    complete = len(known_values) == len(holdings)
    for row in holdings:
        symbol = str(row["symbol"])
        prices = list(histories.get(symbol, []))
        alerts: list[str] = []
        if len(prices) < 45 or row.get("estimated_value_usd") is None:
            rows.append({"symbol": symbol, "status": "data_unavailable", "reasons": [
                "Not enough completed daily prices to assess recent risk."], "observed_drop_pct": None})
            continue
        high = max(p.close for p in prices[-60:])
        latest = prices[-1].close
        drop = (latest / high - 1) * 100
        if drop <= -drop_threshold_pct:
            alerts.append(f"The latest daily price is {abs(drop):.1f}% below its recent high.")
        if complete and sum_values > 0 and _holding_value(row["estimated_value_usd"]) / sum_values > 0.30:
            alerts.append("This holding exceeds 30% of the recorded portfolio's latest estimated value.")
        change = row.get("unrealized_gain_pct")
        if isinstance(change, (int, float)) and change <= -15:
            alerts.append("The recorded holding is down at least 15% versus its recorded purchase cost.")
        rows.append({
            "symbol": symbol, "status": "review_exit_rules" if alerts else "no_rule_triggered",
            "observed_drop_pct": round(drop, 2), "reasons": alerts or [
                "No predefined review threshold triggered; this does not guarantee safety."],
        })
    return rows
