"""Optional SIC industry evidence is stable and cannot bypass existing gates."""

from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api import research_dashboard as research
from app.market_data.sec_identity import SecFiler, SecReference
from app.market_data.sec_industry import SicEntry, SicReference

NOW = datetime(2026, 11, 15, 7, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def]
        return NOW if tz is None else NOW.astimezone(tz)


def client() -> TestClient:
    app = FastAPI()
    app.include_router(research.router)
    return TestClient(app)


def scanner() -> SimpleNamespace:
    return SimpleNamespace(
        state="complete", completed_at="2026-11-15T07:00:00+00:00",
        latest_session="2026-11-13",
        candidates=[{
            "symbol": ticker, "name": f"{ticker} Common Stock",
            "last_session": "2026-11-13", "adjusted_close": 25.0,
            "annualized_volatility_pct": 30.0, "drawdown_60d_pct": -7.0,
            "approx_daily_dollar_volume": 10_000_000.0,
        } for ticker in ("AAA", "BBB")],
    )


def mock_sources(patch: MonkeyPatch, *, same_sic: bool) -> None:
    ticker = SecReference(NOW, "a" * 64, {
        "AAA": (SecFiler("0000001001", "ALPHA", "Nasdaq"),),
        "BBB": (SecFiler("0000001002", "BETA", "NYSE"),),
    })
    sic = SicReference(NOW, "b" * 64, "a" * 64, {
        "0000001001": SicEntry("3571", "Computers"),
        "0000001002": SicEntry("3571" if same_sic else "7372", "Computers" if same_sic else "Software"),
    })
    patch.setattr(research, "load_reference", lambda _root: ticker)
    patch.setattr(research, "load_industry_reference", lambda _root: sic)


def setup(patch: MonkeyPatch) -> None:
    patch.setattr(research, "datetime", Clock)
    patch.setattr(research._MANAGER, "snapshot", scanner)


def test_no_extra_source_requests_without_opt_in() -> None:
    with MonkeyPatch.context() as patch:
        setup(patch)
        patch.setattr(research, "load_industry_reference", lambda _root: (_ for _ in ()).throw(
            AssertionError("No source read should happen by default")))
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": True,
        })
        assert response.status_code == 200
        assert response.json()["sec_industry_review"] is None


def test_optional_sic_rejects_second_same_industry_to_cash() -> None:
    with MonkeyPatch.context() as patch:
        setup(patch)
        mock_sources(patch, same_sic=True)
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": True,
            "require_sec_industry": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["sec_identity_review"]["approved_symbols"] == ["AAA", "BBB"]
        assert data["sec_industry_review"]["approved_symbols"] == ["AAA"]
        assert [(row["symbol"], row["amount_usd"]) for row in data["allocation"]] == [
            ("SPY", "65.00"), ("AAA", "10.00"), (None, "25.00"),
        ]


def test_distinct_industry_allows_two_positions() -> None:
    with MonkeyPatch.context() as patch:
        setup(patch)
        mock_sources(patch, same_sic=False)
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": True,
            "require_sec_industry": True,
        })
        assert [row["amount_usd"] for row in response.json()["allocation"]] == [
            "65.00", "10.00", "10.00", "15.00",
        ]


def test_missing_sic_fails_closed_and_does_not_request_history(tmp_path: Path) -> None:
    with MonkeyPatch.context() as patch:
        setup(patch)
        patch.setattr(research, "_research_root", lambda: tmp_path)
        patch.setattr(research, "AlpacaHistoryClient", lambda _settings: (_ for _ in ()).throw(
            AssertionError("Missing industry cannot request history")))
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": True,
            "require_sec_industry": True, "require_historical_comovement": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["sec_identity_review"]["status"] == "unavailable"
        assert data["sec_industry_review"]["status"] == "unavailable"
        assert [r["amount_usd"] for r in data["allocation"]] == ["65.00", "35.00"]


def test_sic_not_required_when_experimental_disabled() -> None:
    with MonkeyPatch.context() as patch:
        setup(patch)
        patch.setattr(research, "load_industry_reference", lambda _root: (_ for _ in ()).throw(
            AssertionError("No SIC read for ordinary ETF/cash scenario")))
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "require_sec_industry": True,
        })
        assert response.status_code == 200
        assert response.json()["sec_industry_review"] is None
