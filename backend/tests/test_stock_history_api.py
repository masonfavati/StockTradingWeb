"""Historical API stays separate from Find Opportunities and protects Alpaca calls."""

from datetime import date
from decimal import Decimal

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api import stock_history
from app.market_data.history_client import DailyBar, HistoricalDataError


def app_client() -> TestClient:
    app = FastAPI()
    app.include_router(stock_history.router)
    return TestClient(app)


class FakeClient:
    def __init__(self) -> None:
        self.calls = 0

    def pages(self, symbols, **kwargs):  # type: ignore[no-untyped-def]
        self.calls += 1
        yield [DailyBar(
            symbol=symbols[0], session_date=date(2026, 11, 13),
            bar_timestamp=stock_history.datetime.now(stock_history.UTC),
            open_price=Decimal(100), high_price=Decimal(100),
            low_price=Decimal(100), close_price=Decimal(100), volume=1200,
            trade_count=100, vwap=None,
        )]


def reset_cache() -> None:
    stock_history._cache.clear()
    stock_history._recent_fetches.clear()


def test_any_valid_symbol_fetches_without_scanner_or_journal(monkeypatch: MonkeyPatch) -> None:
    reset_cache()
    provider = FakeClient()
    monkeypatch.setattr(stock_history, 'AlpacaHistoryClient', lambda settings: provider)
    result = app_client().get('/api/research/stock-history/ZZZZ?period=1y')
    assert result.status_code == 200
    assert result.json()['symbol'] == 'ZZZZ'
    assert result.json()['price_forecast'] is None
    assert provider.calls == 1
    assert app_client().get('/api/research/stock-history/zzzz?period=1y').status_code == 200
    assert provider.calls == 1  # ten-minute cache, no duplicate broker requests
    reset_cache()


def test_invalid_symbol_or_period_rejected_without_provider_call(monkeypatch: MonkeyPatch) -> None:
    reset_cache()
    monkeypatch.setattr(stock_history, 'AlpacaHistoryClient',
                        lambda settings: (_ for _ in ()).throw(AssertionError('provider called')))
    assert app_client().get('/api/research/stock-history/INVALID!!').status_code == 422
    assert app_client().get('/api/research/stock-history/AAPL?period=10y').status_code == 422
    reset_cache()


def test_history_provider_error_does_not_leak_credentials(monkeypatch: MonkeyPatch) -> None:
    reset_cache()

    class Failed:
        def pages(self, *a, **kwargs):  # type: ignore[no-untyped-def]
            raise HistoricalDataError('SECRET_TOKEN provider account')
            yield  # pragma: no cover

    monkeypatch.setattr(stock_history, 'AlpacaHistoryClient', lambda settings: Failed())
    result = app_client().get('/api/research/stock-history/AAPL')
    assert result.status_code == 503
    assert 'SECRET_TOKEN' not in result.text
    reset_cache()


def test_bounded_unique_request_rate_limit(monkeypatch: MonkeyPatch) -> None:
    reset_cache()
    monkeypatch.setattr(stock_history, 'AlpacaHistoryClient',
                        lambda settings: (_ for _ in ()).throw(AssertionError('provider called')))
    now = stock_history.time.monotonic()
    stock_history._recent_fetches.extend([now] * stock_history._MAX_FETCHES_PER_MINUTE)
    assert app_client().get('/api/research/stock-history/AAPL').status_code == 429
    reset_cache()
