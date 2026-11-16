"""Research allocations always sum to the user's budget and cap concentration."""

import math
from datetime import date, timedelta
from decimal import Decimal

from app.analysis.growth_allocation import build_diversified_research_plan
from app.analysis.historical_growth import PricePoint


def history(mult: float) -> list[PricePoint]:
    return [PricePoint(date(2026, 1, 1) + timedelta(days=i),
                       100 * (1 + 0.001 * i) * (1 + 0.05 * math.sin(i * mult)))
            for i in range(200)]


def example(**options: object) -> dict:
    ranked = [
        {"symbol": "AAA", "estimated_change_pct": 15.0, "historical_analogue_low_pct": -20,
         "historical_analogue_high_pct": 28, "backtest": {}},
        {"symbol": "BBB", "estimated_change_pct": 12.0, "historical_analogue_low_pct": -18,
         "historical_analogue_high_pct": 22, "backtest": {}},
    ]
    return build_diversified_research_plan(
        Decimal("100.00"), style="balanced", horizon="long", max_loss_usd=None,
        allow_exploratory=True, ranked=ranked,
        histories={"AAA": history(0.16), "BBB": history(0.31)}, benchmark=None,
        **options,
    )


def test_cent_exact_and_diversified() -> None:
    plan = example()
    assert sum(Decimal(row["amount_usd"]) for row in plan["allocation"]) == Decimal(100)
    assert all(Decimal(row["amount_usd"]) <= 10 for row in plan["allocation"]
               if row["category"] == "experimental_stock")
    assert plan["current_model_status"] == "historical_backtest_only_not_prospectively_validated"


def test_short_horizon_does_not_put_near_term_cash_in_stocks() -> None:
    result = build_diversified_research_plan(
        Decimal(100), style="growth", horizon="short", max_loss_usd=None,
        allow_exploratory=True, ranked=[], histories={}, benchmark=None,
    )
    assert result["invested_usd"] == "0.00"
    assert result["cash_usd"] == "100.00"


def test_nominal_loss_limit_caps_risky_principal() -> None:
    result = build_diversified_research_plan(
        Decimal(100), style="growth", horizon="long", max_loss_usd=Decimal(5),
        allow_exploratory=True, ranked=[], histories={}, benchmark=None,
    )
    assert result["invested_usd"] == "5.00"
    assert result["cash_usd"] == "95.00"


def test_negative_mktx_forecast_never_receives_stock_dollars() -> None:
    """A listed negative forecast is informative research, not an allocation."""
    ranked = [
        {"symbol": "MKTX", "estimated_change_pct": -11.7,
         "historical_analogue_low_pct": -30,
         "historical_analogue_high_pct": 12, "backtest": {}},
        {"symbol": "AAA", "estimated_change_pct": 35.0,
         "historical_analogue_low_pct": -12,
         "historical_analogue_high_pct": 42, "backtest": {}},
    ]
    plan = build_diversified_research_plan(
        Decimal(2500), style="balanced", horizon="long", max_loss_usd=None,
        allow_exploratory=True, ranked=ranked,
        histories={"MKTX": history(0.19), "AAA": history(0.16)},
        benchmark={"horizons": {"6m": {"estimated_change_pct": 3.2}}},
    )
    assert all(row["symbol"] != "MKTX" for row in plan["allocation"])
    assert any(row["symbol"] == "MKTX" and "not positive" in row["reason"]
               for row in plan["declined"])
    assert sum(Decimal(row["amount_usd"]) for row in plan["allocation"]) == Decimal(2500)


def test_nonpositive_spy_forecast_keeps_core_dollars_as_cash() -> None:
    for estimate in (-11.7, 0.0):
        plan = build_diversified_research_plan(
            Decimal(2500), style="balanced", horizon="long", max_loss_usd=None,
            allow_exploratory=False, ranked=[], histories={},
            benchmark={"horizons": {"6m": {"estimated_change_pct": estimate}}},
        )
        assert plan["invested_usd"] == "0.00"
        assert plan["cash_usd"] == "2500.00"
        assert not any(row["symbol"] == "SPY" for row in plan["allocation"])
        assert any(row["symbol"] == "SPY" and "not positive" in row["reason"]
                   for row in plan["declined"])


def test_positive_spy_and_negative_stock_never_redirect_negative_stock_slices() -> None:
    plan = build_diversified_research_plan(
        Decimal(2500), style="balanced", horizon="long", max_loss_usd=None,
        allow_exploratory=True,
        ranked=[{"symbol": "MKTX", "estimated_change_pct": -11.7,
                 "historical_analogue_low_pct": -20,
                 "historical_analogue_high_pct": 10, "backtest": {}}],
        histories={"MKTX": history(0.16)},
        benchmark={"horizons": {"6m": {"estimated_change_pct": 5.0}}},
    )
    assert plan["invested_usd"] == "1375.00"
    assert plan["cash_usd"] == "1125.00"
    assert {item["category"] for item in plan["allocation"]} == {"diversified_core", "cash"}
