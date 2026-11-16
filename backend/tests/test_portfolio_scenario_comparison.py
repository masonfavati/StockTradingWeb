"""Three budget approaches share inputs; maximum-change never bypasses safety gates."""

import math
from datetime import date, timedelta
from decimal import Decimal

import pytest

from app.analysis.growth_allocation import build_diversified_research_plan
from app.analysis.historical_growth import PricePoint
from app.analysis.max_growth_search import build_max_model_growth_plan
from app.analysis.portfolio_comparison import compare_scenarios


def prices(speed: float) -> list[PricePoint]:
    start = date(2024, 1, 1)
    return [
        PricePoint(start + timedelta(days=i), 100 * (1 + i / 1500) * (1 + 0.03 * math.sin(i * speed)))
        for i in range(490)
    ]


def proposal(symbol: str, change: float) -> dict[str, object]:
    return {
        "symbol": symbol,
        "estimated_change_pct": change,
        "historical_analogue_low_pct": -11.0,
        "historical_analogue_high_pct": 32.0,
        "backtest": {},
    }


def three_approaches(
    *, cap: Decimal | None = None, spy_change: float = 5.0,
    use_stocks: bool = True,
) -> tuple[dict[str, dict], dict[str, list[PricePoint]]]:
    histories = {"SPY": prices(0.04), "AAA": prices(0.13), "BBB": prices(0.21), "MKTX": prices(0.33)}
    ranked = [proposal("AAA", 32), proposal("BBB", 19), proposal("MKTX", -11.7)]
    plans = {
        mode: build_diversified_research_plan(
            Decimal(2500), style="balanced", horizon="long", max_loss_usd=cap,
            allow_exploratory=use_stocks and mode != "core_only",
            ranked=ranked, histories=histories,
            benchmark={"horizons": {"6m": {"estimated_change_pct": spy_change}}},
            allocation_mode=mode,
        ) for mode in ("combined", "core_only")
    }
    plans["max_model_change"] = build_max_model_growth_plan(
        Decimal(2500), style="balanced", horizon="long", max_loss_usd=cap,
        allow_exploratory=use_stocks, ranked=ranked, histories=histories,
        benchmark={"horizons": {"6m": {"estimated_change_pct": spy_change}}},
    )
    return plans, histories


def test_three_scenarios_preserve_budget_and_negative_estimate_exclusion() -> None:
    plans, histories = three_approaches()
    mixed = plans["combined"]
    core = plans["core_only"]
    best = plans["max_model_change"]
    assert core["invested_usd"] == "1375.00"
    assert not any(row["category"] == "experimental_stock" for row in core["allocation"])
    assert best["combination_analysis"]["combinations_considered"] >= 3
    assert Decimal(best["combination_analysis"]["illustrative_model_gain_usd"]) >= (
        Decimal(mixed["combination_analysis"]["illustrative_model_gain_usd"])
    )
    assert Decimal(best["combination_analysis"]["illustrative_model_gain_usd"]) >= (
        Decimal(core["combination_analysis"]["illustrative_model_gain_usd"])
    )
    assert Decimal(mixed["invested_usd"]) >= Decimal(core["invested_usd"])
    for plan in plans.values():
        assert sum(Decimal(row["amount_usd"]) for row in plan["allocation"]) == Decimal(2500)
        assert all(row["symbol"] != "MKTX" for row in plan["allocation"])
        assert all(
            Decimal(row["amount_usd"]) <= Decimal(250)
            for row in plan["allocation"] if row["category"] == "experimental_stock"
        )
    comparison = compare_scenarios(plans, histories, stock_allocation_authorized=True)
    assert [row["id"] for row in comparison["approaches"]] == [
        "combined", "core_only", "max_model_change",
    ]
    assert all(row["available"] for row in comparison["approaches"])
    assert all(row["illustrative_model_gain_usd"] is not None for row in comparison["approaches"])
    assert all(row["past_window_range"] is not None for row in comparison["approaches"])
    assert all(row["past_window_range"]["windows_compared"] >= 3
               for row in comparison["approaches"])


def test_same_affordable_loss_ceiling_caps_all_approaches() -> None:
    plans, histories = three_approaches(cap=Decimal(100))
    comparison = compare_scenarios(plans, histories, stock_allocation_authorized=True)
    for approach in comparison["approaches"]:
        assert Decimal(approach["invested_usd"]) <= Decimal(100)
        assert Decimal(approach["invested_usd"]) + Decimal(approach["cash_usd"]) == Decimal(2500)


def test_nonpositive_spy_has_no_spy_allocation_in_any_approach() -> None:
    plans, _ = three_approaches(spy_change=-5)
    for plan in plans.values():
        assert not any(row["symbol"] == "SPY" for row in plan["allocation"])
    assert plans["core_only"]["cash_usd"] == "2500.00"
    assert any(row["category"] == "experimental_stock" for row in plans["max_model_change"]["allocation"])


def test_unverified_or_unchecked_stocks_do_not_appear_as_a_better_plan() -> None:
    plans, histories = three_approaches(use_stocks=False)
    comparison = compare_scenarios(plans, histories, stock_allocation_authorized=False)
    optimal = comparison["approaches"][2]
    assert optimal["available"] is False
    assert optimal["illustrative_model_gain_usd"] is None
    assert optimal["past_window_range"] is None
    assert optimal["cash_usd"] == "2500.00"
    assert "quality-verified" in optimal["explanation"]


def test_short_term_holding_period_never_adds_risky_positions() -> None:
    ranked = [proposal("AAA", 30)]
    hist = {"AAA": prices(0.13)}
    plans = {
        mode: build_diversified_research_plan(
            Decimal(100), style="growth", horizon="short", max_loss_usd=None,
            allow_exploratory=True, ranked=ranked, histories=hist,
            benchmark={"horizons": {"1m": {"estimated_change_pct": 5}}},
            allocation_mode=mode,
        ) for mode in ("combined", "core_only")
    }
    plans["max_model_change"] = build_max_model_growth_plan(
        Decimal(100), style="growth", horizon="short", max_loss_usd=None,
        allow_exploratory=True, ranked=ranked, histories=hist,
        benchmark={"horizons": {"1m": {"estimated_change_pct": 5}}},
    )
    assert all(plan["cash_usd"] == "100.00" for plan in plans.values())

def test_incomplete_history_never_invents_historical_downside() -> None:
    plans, histories = three_approaches()
    result = compare_scenarios(plans, {"SPY": histories["SPY"][:2]}, stock_allocation_authorized=True)
    assert all(row["past_window_range"] is None for row in result["approaches"])


def test_missing_scenario_is_rejected() -> None:
    plans, histories = three_approaches()
    with pytest.raises(ValueError, match="All three"):
        compare_scenarios({"combined": plans["combined"]}, histories, stock_allocation_authorized=True)
