"""Exploratory metrics must not accidentally become fabricated forecasts."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

from app.analysis.opportunities import describe_candidate, shortlist
from app.market_data.history_client import DailyBar


def bars(*, count: int = 65, price: int = 100, volume: int = 250000) -> list[DailyBar]:
    output = []
    day = date(2026, 1, 1)
    for i in range(count):
        # Rising, nonzero-volatility series (unrealistically regular but deterministic).
        close = Decimal(price) + Decimal(i * 2) + Decimal(i % 3)
        output.append(DailyBar(
            symbol="AAPL",
            session_date=day + timedelta(days=i),
            bar_timestamp=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(days=i),
            open_price=close,
            high_price=close + 1,
            low_price=close - 1,
            close_price=close,
            volume=volume,
            trade_count=1000,
            vwap=close,
        ))
    return output


def test_metrics_have_explicit_history_basis() -> None:
    result = describe_candidate("AAPL", "Apple Inc.", bars())
    assert result is not None
    assert result.return_20d_pct > 0
    assert result.return_60d_pct > result.return_20d_pct
    assert result.annualized_volatility_pct > 0
    assert result.research_score > 0
    assert result.last_session == date(2026, 1, 1) + timedelta(days=64)


def test_inadequate_data_is_not_ranked() -> None:
    assert describe_candidate("AAPL", "Apple", bars(count=60)) is None


def test_low_share_price_does_not_mean_good_opportunity() -> None:
    assert describe_candidate("AAPL", "Apple", bars(price=1, count=61, volume=1)) is None


def test_thinly_traded_stock_is_excluded() -> None:
    assert describe_candidate("AAPL", "Apple", bars(volume=1)) is None


def test_duplicate_day_is_rejected() -> None:
    rows = bars()
    rows[1] = rows[0]
    assert describe_candidate("AAPL", "Apple", rows) is None


def test_shortlist_is_stable_and_limited() -> None:
    first = describe_candidate("AAA", "A", bars())
    second = describe_candidate("BBB", "B", bars())
    assert first is not None and second is not None
    assert [row.symbol for row in shortlist([second, first], limit=1)] == ["AAA"]
