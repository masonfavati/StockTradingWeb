"""Independent chart history: bounds, provenance, dates, benchmark and no made-up forecasts."""

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.analysis.stock_history_chart import (
    ChartHistoryError,
    build_stock_history,
    completed_cutoff,
    validate_symbol,
)
from app.market_data.history_client import DailyBar

NOW = datetime(2026, 11, 15, 20, tzinfo=UTC)


def bar(symbol: str, day: date, price: str) -> DailyBar:
    value = Decimal(price)
    return DailyBar(
        symbol=symbol, session_date=day, bar_timestamp=datetime(2026, 11, 13, tzinfo=UTC),
        open_price=value, high_price=value, low_price=value, close_price=value,
        volume=10000, trade_count=None, vwap=None,
    )


class Provider:
    def __init__(self, rows: list[DailyBar], *, page_size: int = 3) -> None:
        self.rows = rows
        self.page_size = page_size
        self.calls: list[tuple] = []

    def pages(self, symbols, *, start, end, feed, adjustment, page_limit):  # type: ignore[no-untyped-def]
        self.calls.append((symbols, start, end, feed, adjustment, page_limit))
        for start_i in range(0, len(self.rows), self.page_size):
            yield self.rows[start_i:start_i + self.page_size]


def test_fetches_older_historical_closes_without_any_scan() -> None:
    provider = Provider([bar('AAPL', date(2026, 11, 11), '101'),
                         bar('AAPL', date(2026, 11, 12), '104'),
                         bar('AAPL', date(2026, 11, 13), '103')])
    result = build_stock_history(provider, symbol=' aapl ', period='1m', compare_spy=False, now=NOW)
    assert result['symbol'] == 'AAPL'
    assert result['session_count'] == 3
    assert result['last_session'] == '2026-11-13'
    assert result['first_adjusted_close_usd'] == 101
    assert result['last_adjusted_close_usd'] == 103
    assert result['period_change_pct'] == 1.98
    assert result['feed'] == 'sip' and result['adjustment'] == 'all'
    assert result['provider'] == 'alpaca'
    assert result['price_forecast'] is None
    assert result['forecast_status'] == 'no_validated_price_forecast'
    symbols, start, end, feed, adjustment, limit = provider.calls[0]
    assert symbols == ['AAPL']
    assert end.astimezone(ZoneInfo('America/New_York')).date() == date(2026, 11, 14)
    assert start == date(2026, 11, 14) - timedelta(days=40)
    assert (feed, adjustment, limit) == ('sip', 'all', 1000)


def test_comparison_uses_only_matching_real_sessions() -> None:
    rows = [bar('AAA', date(2026, 11, 10), '20'),
            bar('AAA', date(2026, 11, 11), '22'),
            bar('AAA', date(2026, 11, 13), '24'),
            bar('SPY', date(2026, 11, 11), '100'),
            bar('SPY', date(2026, 11, 12), '101'),
            bar('SPY', date(2026, 11, 13), '110')]
    result = build_stock_history(Provider(rows, page_size=4), symbol='AAA',
                                 period='3m', compare_spy=True, now=NOW)
    assert result['benchmark_available'] is True
    assert result['benchmark_anchor_session'] == '2026-11-11'
    assert [row['session_date'] for row in result['spy_benchmark']] == ['2026-11-11', '2026-11-13']
    assert [row['normalized_index'] for row in result['spy_benchmark']] == [100, 110]
    assert [row['normalized_index'] for row in result['bars']] == [100, 109.0909]
    assert result['first_session'] == '2026-11-11'
    assert result['warning'] is not None


def test_missing_comparable_spy_never_uses_guessed_prices() -> None:
    result = build_stock_history(
        Provider([bar('AAA', date(2026, 11, 13), '20'),
                  bar('SPY', date(2026, 11, 12), '600')]),
        symbol='AAA', period='1m', compare_spy=True, now=NOW,
    )
    assert result['benchmark_available'] is False
    assert result['spy_benchmark'] == []
    assert result['warning'] is not None


def test_no_data_is_explicitly_empty_not_a_zero_price() -> None:
    result = build_stock_history(Provider([]), symbol='XYZ', period='1y', compare_spy=False, now=NOW)
    assert result['bars'] == []
    assert result['last_adjusted_close_usd'] is None
    assert result['period_change_pct'] is None
    assert result['warning'] is not None


@pytest.mark.parametrize('bad', ['DROP TABLE', '', '../SPY', 'AAA/BBB', 'a' * 21, '$SPY'])
def test_invalid_symbols_rejected_before_provider_request(bad: str) -> None:
    provider = Provider([])
    with pytest.raises(ChartHistoryError):
        build_stock_history(provider, symbol=bad, period='1y', compare_spy=False, now=NOW)
    assert provider.calls == []


def test_ticker_normalization_does_not_map_historic_issuer() -> None:
    assert validate_symbol(' brk.b ') == 'BRK.B'
    assert validate_symbol('BRK-B') == 'BRK-B'


def test_rejects_future_incomplete_prices() -> None:
    provider = Provider([bar('AAA', date(2026, 11, 15), '20')])
    with pytest.raises(ChartHistoryError, match='future or incomplete'):
        build_stock_history(provider, symbol='AAA', period='1y', compare_spy=False, now=NOW)


def test_rejects_duplicate_session() -> None:
    provider = Provider([bar('AAA', date(2026, 11, 13), '20'),
                         bar('AAA', date(2026, 11, 13), '21')])
    with pytest.raises(ChartHistoryError, match='Duplicate'):
        build_stock_history(provider, symbol='AAA', period='1y', compare_spy=False, now=NOW)


def test_rejects_unexpected_symbols() -> None:
    with pytest.raises(ChartHistoryError, match='unexpected'):
        build_stock_history(Provider([bar('WRONG', date(2026, 11, 13), '20')]),
                            symbol='AAA', period='1y', compare_spy=False, now=NOW)


def test_rejects_page_explosion() -> None:
    rows = [bar('AAA', date(2026, 11, 13) - timedelta(days=i), '20') for i in range(8)]
    with pytest.raises(ChartHistoryError, match='capacity'):
        build_stock_history(Provider(rows, page_size=1), symbol='AAA',
                            period='1y', compare_spy=False, now=NOW)


def test_rejects_nonfinite_and_huge_prices() -> None:
    with pytest.raises(ChartHistoryError, match='bounds'):
        build_stock_history(Provider([bar('AAA', date(2026, 11, 13), 'NaN')]),
                            symbol='AAA', period='1y', compare_spy=False, now=NOW)


def test_cutoff_safe_across_dst_and_requires_timezone() -> None:
    now = datetime(2026, 3, 8, 15, tzinfo=UTC)  # NY daylight-saving transition
    cutoff = completed_cutoff(now)
    assert cutoff.astimezone(ZoneInfo('America/New_York')).date() == date(2026, 3, 7)
    assert cutoff.astimezone(ZoneInfo('America/New_York')).hour == 23
    with pytest.raises(ValueError, match='timezone'):
        completed_cutoff(datetime(2026, 3, 8))


def test_benchmark_is_not_fetched_when_primary_is_spy() -> None:
    provider = Provider([bar('SPY', date(2026, 11, 13), '600')])
    result = build_stock_history(provider, symbol='SPY', period='1m', compare_spy=True, now=NOW)
    assert result['benchmark_requested'] is False
    assert result['benchmark_available'] is False
    assert provider.calls[0][0] == ['SPY']
