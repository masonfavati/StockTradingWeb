"""Optional history request is bounded, with no surprise provider calls."""

from datetime import UTC, datetime
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch
from test_portfolio_comovement import SESSION, Provider

from app.api import research_dashboard as research
from app.market_data.history_client import HistoricalDataError

NOW = datetime(2026, 11, 15, 2, tzinfo=UTC)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def]
        return NOW if tz is None else NOW.astimezone(tz)


def make_app() -> TestClient:
    app = FastAPI()
    app.include_router(research.router)
    return TestClient(app)


def fake_snapshot() -> SimpleNamespace:
    return SimpleNamespace(
        state="complete", completed_at="2026-11-14T21:00:00+00:00",
        latest_session=SESSION.isoformat(),
        candidates=[
            {
                "symbol": symbol, "name": f"{symbol} Corporation Common Stock",
                "last_session": SESSION.isoformat(), "adjusted_close": 20.0,
                "annualized_volatility_pct": 35.0, "drawdown_60d_pct": -8.0,
                "approx_daily_dollar_volume": 12_000_000.0,
            } for symbol in ("AAA", "BBB")
        ],
    )


def test_default_request_does_not_contact_history_provider() -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", fake_snapshot)
        patch.setattr(research, "AlpacaHistoryClient", lambda _settings: (_ for _ in ()).throw(
            AssertionError("No historical download expected")))
        result = make_app().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "allow_experimental_stocks": True,
        })
        assert result.status_code == 200
        assert result.json()["comovement_review"] is None
        assert [r["amount_usd"] for r in result.json()["allocation"]] == [
            "65.00", "10.00", "10.00", "15.00",
        ]
    finally:
        patch.undo()


def test_explicit_correlation_check_excludes_highly_correlated_second_stock() -> None:
    patch = MonkeyPatch()
    try:
        provider = Provider()
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", fake_snapshot)
        patch.setattr(research, "AlpacaHistoryClient", lambda _settings: provider)
        result = make_app().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "allow_experimental_stocks": True,
            "require_historical_comovement": True,
        })
        assert result.status_code == 200
        data = result.json()
        assert [r["symbol"] for r in data["allocation"]] == ["SPY", "AAA", None]
        assert [r["amount_usd"] for r in data["allocation"]] == ["65.00", "10.00", "25.00"]
        assert data["comovement_review"]["status"] == "checked"
        assert len(provider.calls) == 1
    finally:
        patch.undo()


def test_explicit_correlation_provider_failure_keeps_risky_stocks_as_cash() -> None:
    patch = MonkeyPatch()
    try:
        class Down:
            def pages(self, *args, **kwargs):  # type: ignore[no-untyped-def]
                raise HistoricalDataError("provider failed with private data")
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", fake_snapshot)
        patch.setattr(research, "AlpacaHistoryClient", lambda _settings: Down())
        result = make_app().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "allow_experimental_stocks": True,
            "require_historical_comovement": True,
        })
        assert result.status_code == 200
        data = result.json()
        assert [r["amount_usd"] for r in data["allocation"]] == ["65.00", "35.00"]
        assert data["comovement_review"]["status"] == "unavailable"
        assert "private" not in result.text
    finally:
        patch.undo()


def test_no_experimental_optin_does_not_contact_provider_even_with_flag() -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", fake_snapshot)
        patch.setattr(research, "AlpacaHistoryClient", lambda _settings: (_ for _ in ()).throw(
            AssertionError("No historical download expected")))
        result = make_app().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "allow_experimental_stocks": False,
            "require_historical_comovement": True,
        })
        assert result.status_code == 200
        assert result.json()["comovement_review"] is None
    finally:
        patch.undo()
