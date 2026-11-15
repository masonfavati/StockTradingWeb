"""The HTTP API validates both user-entered constraints and never starts a scan."""

from types import SimpleNamespace

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api import research_dashboard as research


def client() -> TestClient:
    app = FastAPI()
    app.include_router(research.router)
    return TestClient(app)


def test_budget_limit_and_horizon_via_api_without_a_scan() -> None:
    with MonkeyPatch.context() as patch:
        patch.setattr(research._MANAGER, "snapshot", lambda: SimpleNamespace(
            state="idle", completed_at=None, latest_session=None, candidates=[],
        ))
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "style": "balanced", "horizon": "long",
            "max_loss_usd": "20.00", "allow_experimental_stocks": False,
        })
    assert response.status_code == 200
    plan = response.json()
    assert [row["amount_usd"] for row in plan["allocation"]] == ["20.00", "80.00"]
    assert plan["max_loss_usd"] == "20.00"
    assert plan["loss_cap_binding"] is True


@pytest.mark.parametrize("horizon", ["invalid", "", "tomorrow"])
def test_rejects_unrecognized_horizons(horizon: str) -> None:
    assert client().post("/api/research/budget-plan", json={
        "budget_usd": "100", "horizon": horizon,
    }).status_code == 422


@pytest.mark.parametrize("value", ["100.01", "-1", "0.001", "NaN", "Infinity"])
def test_rejects_inapplicable_max_loss(value: str) -> None:
    assert client().post("/api/research/budget-plan", json={
        "budget_usd": "100", "max_loss_usd": value,
    }).status_code == 422


def test_zero_loss_limit_returns_all_cash() -> None:
    response = client().post("/api/research/budget-plan", json={
        "budget_usd": "100", "max_loss_usd": "0", "horizon": "long",
    })
    assert response.status_code == 200
    result = response.json()
    assert result["modeled_risky_principal_usd"] == "0.00"
    assert result["unallocated_cash_usd"] == "100.00"
