"""The model cannot override any existing planner evidence or spending gate."""

from datetime import UTC, datetime
from decimal import Decimal
from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import research_dashboard as research

NOW = datetime(2026, 11, 15, 7, tzinfo=UTC)


class Clock(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def]
        return NOW if tz is None else NOW.astimezone(tz)


def client() -> TestClient:
    app = FastAPI()
    app.include_router(research.router)
    return TestClient(app)


def candidate(symbol: str, score: float) -> dict:
    return {
        "symbol": symbol, "name": f"{symbol} Corporation Common Stock",
        "last_session": "2026-11-13", "adjusted_close": 25.0,
        "return_20d_pct": 10.0, "return_60d_pct": 22.0,
        "annualized_volatility_pct": 30.0, "drawdown_60d_pct": -8.0,
        "approx_daily_dollar_volume": 10_000_000.0, "research_score": score,
    }


def setup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(research, "datetime", Clock)
    monkeypatch.setattr(research._MANAGER, "snapshot", lambda: SimpleNamespace(
        state="complete", completed_at="2026-11-15T07:00:00+00:00",
        latest_session="2026-11-13",
        candidates=[candidate("AAA", 0.9), candidate("BBB", 0.8), candidate("CCC", 0.7)],
    ))


def request(**extra: object) -> dict:
    return {"budget_usd": "100", "allow_experimental_stocks": True, **extra}


def test_default_planner_never_loads_training(monkeypatch: pytest.MonkeyPatch) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: pytest.fail(
        "Prediction journal should not be queried by ordinary budget plan"))
    response = client().post("/api/research/budget-plan", json=request())
    assert response.status_code == 200
    data = response.json()
    assert data["prediction_review"] is None
    assert [r["symbol"] for r in data["allocation"]] == ["SPY", "AAA", "BBB", None]


def test_no_matured_outcomes_fails_closed_without_new_market_queries(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(research, "report_from_verified_windows", lambda *a, **kw: {
        "status": "insufficient_evidence",
    })
    monkeypatch.setattr(research, "AlpacaHistoryClient", lambda *a: pytest.fail(
        "Rejected predictions must not call market history"))
    response = client().post("/api/research/budget-plan", json=request(
        require_prediction=True, require_historical_comovement=True,
    ))
    assert response.status_code == 200
    data = response.json()
    assert data["prediction_required"]
    assert data["prediction_review"]["status"] == "insufficient_training_before_signal"
    assert [(row["symbol"], row["amount_usd"]) for row in data["allocation"]] == [
        ("SPY", "65.00"), (None, "35.00"),
    ]


def test_verified_prediction_can_rerank_all_eligible_candidates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(research, "report_from_verified_windows", lambda *a, **kw: {
        "status": "research_gate_passed",
    })

    def model_review(candidates, session, windows, report):
        assert {r["symbol"] for r in candidates} == {"AAA", "BBB", "CCC"}
        assert session == "2026-11-13"
        assert windows == []
        return {
            "status": "research_gate_passed", "requested_symbols": ["AAA", "BBB", "CCC"],
            "approved_symbols": ["CCC", "AAA"], "proposed_slot_count": 2,
            "scores": [
                {"symbol": "AAA", "estimated_probability_beating_spy": .65, "training_prior": .50},
                {"symbol": "BBB", "estimated_probability_beating_spy": .44, "training_prior": .50},
                {"symbol": "CCC", "estimated_probability_beating_spy": .73, "training_prior": .50},
            ], "excluded": [], "caveat": "Research only.",
        }

    monkeypatch.setattr(research, "review_prediction", model_review)
    response = client().post("/api/research/budget-plan", json=request(require_prediction=True))
    assert response.status_code == 200
    allocation = response.json()["allocation"]
    assert [(row["symbol"], row["amount_usd"]) for row in allocation] == [
        ("SPY", "65.00"), ("CCC", "10.00"), ("AAA", "10.00"), (None, "15.00"),
    ]


def test_one_predicted_stock_keeps_other_slot_as_cash_under_small_risk_cap(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(research, "report_from_verified_windows", lambda *a, **kw: {
        "status": "research_gate_passed",
    })
    monkeypatch.setattr(research, "review_prediction", lambda *a: {
        "status": "research_gate_passed", "requested_symbols": ["AAA", "BBB", "CCC"],
        "approved_symbols": ["AAA"], "proposed_slot_count": 2,
        "scores": [{"symbol": "AAA", "estimated_probability_beating_spy": .7,
                    "training_prior": .5}], "excluded": [], "caveat": "Research only.",
    })
    response = client().post("/api/research/budget-plan", json=request(
        require_prediction=True, max_loss_usd="75",
    ))
    assert response.status_code == 200
    allocation = response.json()["allocation"]
    # Core $65 + half of remaining $10 satellite cap; other half remains cash.
    assert [(row["symbol"], row["amount_usd"]) for row in allocation] == [
        ("SPY", "65.00"), ("AAA", "5.00"), (None, "30.00"),
    ]
    assert Decimal(response.json()["modeled_risky_principal_usd"]) <= Decimal(75)


def test_unavailable_journal_blocks_prediction_but_not_core_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: (_ for _ in ()).throw(
        OSError("Private local journal unavailable")))
    response = client().post("/api/research/budget-plan", json=request(require_prediction=True))
    assert response.status_code == 200
    body = response.json()
    assert body["prediction_review"]["status"] == "unavailable"
    assert body["unallocated_cash_usd"] == "35.00"


def test_no_provider_or_model_read_when_experimental_is_off(monkeypatch: pytest.MonkeyPatch) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: pytest.fail(
        "No model when experimental securities disabled"))
    response = client().post("/api/research/budget-plan", json={
        "budget_usd": "100", "require_prediction": True,
    })
    assert response.status_code == 200
    assert response.json()["prediction_review"] is None


def test_forecast_endpoint_reports_insufficient_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(research, "build_prediction_report", lambda _root: {
        "status": "insufficient_evidence", "completed_compatible_windows": 0,
    })
    response = client().get("/api/research/prediction-validation")
    assert response.status_code == 200
    assert response.json()["completed_compatible_windows"] == 0


def test_corrupt_journal_returns_service_unavailable_not_fake_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(research, "build_prediction_report", lambda _root: (_ for _ in ()).throw(
        OSError("Bad private source")))
    response = client().get("/api/research/prediction-validation")
    assert response.status_code == 503
    assert "Bad private source" not in response.json()["detail"]


def test_request_validation_rejects_string_bool(monkeypatch: pytest.MonkeyPatch) -> None:
    setup(monkeypatch)
    response = client().post("/api/research/budget-plan", json=request(require_prediction="yes"))
    assert response.status_code == 422


def test_model_ranked_candidates_remain_subject_to_sec_industry_concentration(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Model ranking cannot reintroduce a stock the SEC SIC gate excludes."""
    from app.market_data.sec_identity import SecFiler, SecReference
    from app.market_data.sec_industry import SicEntry, SicReference

    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(research, "report_from_verified_windows", lambda *a, **kw: {
        "status": "research_gate_passed",
    })
    monkeypatch.setattr(research, "review_prediction", lambda *a: {
        "status": "research_gate_passed", "requested_symbols": ["AAA", "BBB", "CCC"],
        "approved_symbols": ["CCC", "AAA"], "proposed_slot_count": 2,
        "scores": [
            {"symbol": "CCC", "estimated_probability_beating_spy": 0.70},
            {"symbol": "AAA", "estimated_probability_beating_spy": 0.65},
        ], "excluded": [], "caveat": "Research only.",
    })
    filer_reference = SecReference(NOW, "a" * 64, {
        "CCC": (SecFiler("0000001001", "COMPANY CCC", "Nasdaq"),),
        "AAA": (SecFiler("0000001002", "COMPANY AAA", "NYSE"),),
    })
    sic_reference = SicReference(NOW, "b" * 64, "a" * 64, {
        "0000001001": SicEntry("3571", "Computers"),
        "0000001002": SicEntry("3571", "Computers"),
    })
    monkeypatch.setattr(research, "load_reference", lambda *a: filer_reference)
    monkeypatch.setattr(research, "load_industry_reference", lambda *a: sic_reference)
    response = client().post("/api/research/budget-plan", json=request(
        require_prediction=True, require_sec_industry=True,
    ))
    assert response.status_code == 200
    data = response.json()
    assert data["prediction_review"]["status"] == "research_gate_passed"
    assert data["sec_industry_review"]["approved_symbols"] == ["CCC"]
    assert [(row["symbol"], row["amount_usd"]) for row in data["allocation"]] == [
        ("SPY", "65.00"), ("CCC", "10.00"), (None, "25.00"),
    ]


def test_unvalidated_prediction_plus_sec_and_history_never_fetches_history(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    setup(monkeypatch)
    monkeypatch.setattr(research, "load_verified_windows", lambda *a, **kw: ([], {}))
    monkeypatch.setattr(research, "report_from_verified_windows", lambda *a, **kw: {
        "status": "insufficient_evidence",
    })
    monkeypatch.setattr(research, "AlpacaHistoryClient", lambda *a: pytest.fail(
        "No market history request for a rejected model"))
    response = client().post("/api/research/budget-plan", json=request(
        require_prediction=True, require_sec_industry=True,
        require_historical_comovement=True,
    ))
    assert response.status_code == 200
    assert [row["amount_usd"] for row in response.json()["allocation"]] == [
        "65.00", "35.00",
    ]
