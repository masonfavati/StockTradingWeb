"""No fabricated bars or 'perfect sell' claims in on-demand market history."""

from collections.abc import Iterator
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.analysis.historical_growth import PricePoint
from app.analysis.investing_service import (
    InvestingDataError,
    fetch_growth_histories,
    price_review_alerts,
)
from app.market_data.history_client import DailyBar, HistoryAdjustment, HistoryFeed


def bar(symbol: str, day: date, close: str) -> DailyBar:
    price = Decimal(close)
    return DailyBar(symbol=symbol, session_date=day,
                    bar_timestamp=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
                    open_price=price, high_price=price, low_price=price, close_price=price,
                    volume=1000, trade_count=100, vwap=None)


class Provider:
    def __init__(self, rows: list[DailyBar]):
        self.rows = rows
        self.calls: list[tuple[str, str]] = []

    def pages(self, symbols: list[str], *, start: date, end: datetime,
              feed: HistoryFeed, adjustment: HistoryAdjustment,
              page_limit: int) -> Iterator[list[DailyBar]]:
        self.calls.append((feed, adjustment))
        yield [row for row in self.rows if row.symbol in symbols]


def test_history_fetch_is_independent_of_scan_and_uses_completed_days() -> None:
    now = datetime(2026, 11, 16, 4, tzinfo=UTC)  # Nov 15 in New York
    provider = Provider([bar("AAPL", date(2026, 11, 13), "101")])
    result = fetch_growth_histories(provider, ["AAPL"], now=now, calendar_days=400)
    assert result["AAPL"][-1].close == 101
    assert provider.calls == [("sip", "all")]


def test_unfinished_session_rejected() -> None:
    now = datetime(2026, 11, 16, 4, tzinfo=UTC)
    provider = Provider([bar("AAPL", date(2026, 11, 15), "101")])
    with pytest.raises(InvestingDataError, match="outside"):
        fetch_growth_histories(provider, ["AAPL"], now=now, calendar_days=400)


def test_alerts_only_use_predefined_thresholds() -> None:
    rows = [PricePoint(date(2026, 5, 1) + timedelta(days=i), 100.0)
            for i in range(70)]
    rows[-1] = PricePoint(rows[-1].day, 79.0)
    holdings = [{"symbol": "AAA", "estimated_value_usd": "79.00", "unrealized_gain_pct": -21.0}]
    result = price_review_alerts(holdings, {"AAA": rows})
    assert result[0]["status"] == "review_exit_rules"
    assert "21.0%" in str(result[0]["reasons"])
    with pytest.raises(InvestingDataError):
        price_review_alerts(holdings, {"AAA": rows}, drop_threshold_pct=1)


def test_alerts_reject_unusable_recorded_values() -> None:
    holdings = [{"symbol": "AAA", "estimated_value_usd": "NaN"}]
    with pytest.raises(InvestingDataError, match="holding value"):
        price_review_alerts(holdings, {"AAA": []})
