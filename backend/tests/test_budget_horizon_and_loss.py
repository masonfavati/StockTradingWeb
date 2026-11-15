"""Predeclared horizon and affordable-loss constraints never fabricate investment evidence."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.analysis.budget_planner import (
    BudgetPlanError,
    make_budget_plan,
    validate_max_loss,
)

NOW = datetime(2026, 11, 15, 15, tzinfo=UTC)
IDEAS: list[dict[str, object]] = [
    {
        "symbol": "AAA", "name": "AAA Example Common Stock", "adjusted_close": 20,
        "last_session": "2026-11-13",
        "annualized_volatility_pct": 35.0,
        "drawdown_60d_pct": -8.0,
        "approx_daily_dollar_volume": 12_000_000.0,
    },
    {
        "symbol": "BBB", "name": "BBB Example Ordinary Shares", "adjusted_close": 40,
        "last_session": "2026-11-13",
        "annualized_volatility_pct": 35.0,
        "drawdown_60d_pct": -8.0,
        "approx_daily_dollar_volume": 12_000_000.0,
    },
]


def make(
    amount: str = "100", *, horizon: str = "long", max_loss: str | None = None,
    opt_in: bool = False, style: str = "balanced", scan: str = "complete",
) -> dict[str, object]:
    return make_budget_plan(
        Decimal(amount), style,  # type: ignore[arg-type]
        horizon=horizon,  # type: ignore[arg-type]
        max_loss_usd=Decimal(max_loss) if max_loss is not None else None,
        allow_experimental_stocks=opt_in,
        scan_state=scan,
        scan_completed_at=NOW.isoformat(),
        scan_latest_session="2026-11-13",
        candidates=IDEAS,
        now=NOW,
    )


def amounts(plan: dict[str, object]) -> list[str]:
    return [row["amount_usd"] for row in plan["allocation"]]  # type: ignore[index]


def test_unset_new_inputs_preserve_old_long_term_example() -> None:
    result = make()
    assert amounts(result) == ["65.00", "35.00"]
    assert result["horizon"] == "long"
    assert result["max_loss_usd"] is None
    assert "not a" in str(result["warnings"]).lower()


@pytest.mark.parametrize("style", ["cautious", "balanced", "growth"])
@pytest.mark.parametrize("opt_in", [False, True])
def test_short_horizon_recommends_no_risk_assets(style: str, opt_in: bool) -> None:
    result = make(horizon="short", style=style, opt_in=opt_in)
    assert result["modeled_risky_principal_usd"] == "0.00"
    assert result["total_invested_example_usd"] == "0.00"
    assert result["unallocated_cash_usd"] == "100.00"
    assert result["stress_scenarios"][2]["loss_usd"] == "0.00"  # type: ignore[index]
    assert all(row["category"] != "experimental_stock_idea" for row in result["allocation"])  # type: ignore[index]


@pytest.mark.parametrize("style,expected", [
    ("cautious", ["25.00", "75.00"]),
    ("balanced", ["35.00", "65.00"]),
    ("growth", ["40.00", "60.00"]),
])
def test_medium_horizon_reduces_exposure(style: str, expected: list[str]) -> None:
    assert amounts(make(horizon="medium", style=style)) == expected


def test_medium_horizon_experimental_slice_is_capped_and_opt_in_only() -> None:
    result = make(horizon="medium", opt_in=True)
    assert amounts(result) == ["35.00", "5.00", "5.00", "55.00"]
    assert result["modeled_risky_principal_usd"] == "45.00"


@pytest.mark.parametrize("loss,core,cash", [
    ("0", "0.00", "100.00"),
    ("0.01", "0.01", "99.99"),
    ("25.00", "25.00", "75.00"),
    ("65.00", "65.00", "35.00"),
    ("100.00", "65.00", "35.00"),
])
def test_affordable_loss_caps_core_without_leverage(loss: str, core: str, cash: str) -> None:
    result = make(max_loss=loss)
    assert amounts(result) == [core, cash]
    assert Decimal(result["modeled_risky_principal_usd"]) <= Decimal(loss)  # type: ignore[arg-type]


def test_cap_never_goes_to_satellites_before_diversified_core() -> None:
    result = make(max_loss="70.00", opt_in=True)
    assert amounts(result) == ["65.00", "2.50", "2.50", "30.00"]
    assert result["loss_cap_binding"] is True
    assert result["modeled_risky_principal_usd"] == "70.00"
    assert result["stress_scenarios"][2] == {  # type: ignore[index]
        "decline_percent": 100,
        "loss_usd": "70.00",
        "remaining_budget_usd": "30.00",
    }


def test_max_loss_is_not_reported_as_forecast() -> None:
    result = make(max_loss="20.00", opt_in=True)
    assert amounts(result) == ["20.00", "80.00"]
    assert result["loss_cap_binding"] is True
    assert any("NOT a forecast" in text for text in result["planning_explanations"])  # type: ignore[union-attr]


@pytest.mark.parametrize("invalid", ["-1", "100.01", "0.001", "NaN", "Infinity"])
def test_rejects_invalid_loss_limit(invalid: str) -> None:
    with pytest.raises(BudgetPlanError):
        make(max_loss=invalid)


@pytest.mark.parametrize("invalid", ["-0.01", "0.001", "NaN", "Infinity"])
def test_validator_rejects_bad_loss_inputs(invalid: str) -> None:
    with pytest.raises(BudgetPlanError):
        validate_max_loss(Decimal(invalid), Decimal(100))


def test_unrecognized_horizon_fails_closed() -> None:
    with pytest.raises(BudgetPlanError):
        make(horizon="tomorrow")


@pytest.mark.parametrize("amount", ["0.01", "1.01", "100", "99.99", "1000000.00"])
@pytest.mark.parametrize("horizon", ["short", "medium", "long"])
def test_pennies_and_risk_cap_reconcile_for_all_horizons(amount: str, horizon: str) -> None:
    budget = Decimal(amount)
    cap = (budget / 3).quantize(Decimal("0.01"))
    result = make(amount, horizon=horizon, max_loss=str(cap), opt_in=True)
    assert sum(Decimal(row["amount_usd"]) for row in result["allocation"]) == budget  # type: ignore[index]
    assert Decimal(result["modeled_risky_principal_usd"]) <= cap  # type: ignore[arg-type]
    assert Decimal(result["total_invested_example_usd"]) + Decimal(result["unallocated_cash_usd"]) == budget  # type: ignore[arg-type]


def test_loss_cap_does_not_make_stale_stock_ideas_eligible() -> None:
    result = make(max_loss="100.00", opt_in=True, scan="running")
    assert result["scan_usable_for_ideas"] is False
    assert amounts(result) == ["65.00", "35.00"]


def test_stress_scenarios_are_based_on_risky_dollars_not_entire_budget() -> None:
    result = make(max_loss="25.00")
    assert result["stress_scenarios"] == [
        {"decline_percent": 10, "loss_usd": "2.50", "remaining_budget_usd": "97.50"},
        {"decline_percent": 30, "loss_usd": "7.50", "remaining_budget_usd": "92.50"},
        {"decline_percent": 100, "loss_usd": "25.00", "remaining_budget_usd": "75.00"},
    ]
