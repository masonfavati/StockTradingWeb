"""Guard risk-aware individual-stock allocations and dollar conservation."""

import math
from datetime import date, timedelta
from decimal import Decimal

from app.analysis.growth_allocation import build_diversified_research_plan
from app.analysis.historical_growth import PricePoint


def prices(freq: float) -> list[PricePoint]:
    start = date(2024, 1, 1)
    return [
        PricePoint(start + timedelta(days=i), 100 * (1 + i / 400) * (1 + 0.03 * math.sin(i * freq)))
        for i in range(150)
    ]


def stock(symbol: str, estimate: float, low: float = -10) -> dict:
    return {
        "symbol": symbol,
        "estimated_change_pct": estimate,
        "historical_analogue_low_pct": low,
        "historical_analogue_high_pct": max(estimate, 30),
        "backtest": {},
    }


def plan(ranked: list[dict], *, cap: Decimal | None = None) -> dict:
    return build_diversified_research_plan(
        Decimal(2500), style="balanced", horizon="long", max_loss_usd=cap,
        allow_exploratory=True, ranked=ranked,
        histories={"AAA": prices(0.11), "BBB": prices(0.24), "MKTX": prices(0.31)},
        benchmark={"horizons": {"6m": {"estimated_change_pct": 3.2}}},
    )


def test_different_positive_stocks_receive_explicit_capped_dollar_amounts() -> None:
    result = plan([stock("AAA", 35), stock("BBB", 18)])
    positions = [row for row in result["allocation"] if row["category"] == "experimental_stock"]
    assert {row["symbol"] for row in positions} == {"AAA", "BBB"}
    assert all(0 < Decimal(row["amount_usd"]) <= Decimal(250) for row in positions)
    assert sum(Decimal(row["amount_usd"]) for row in positions) <= Decimal(500)
    assert sum(Decimal(row["amount_usd"]) for row in result["allocation"]) == Decimal(2500)
    assert result["combination_analysis"]["combinations_considered"] >= 3
    assert result["combination_analysis"]["stock_positions_selected"] == 2


def test_negative_mktx_appears_only_as_rejected_research() -> None:
    result = plan([stock("AAA", 35), stock("MKTX", -11.7)])
    assert not any(row["symbol"] == "MKTX" for row in result["allocation"])
    assert any(row["symbol"] == "MKTX" and "not positive" in row["reason"]
               for row in result["declined"])
    assert any(row["symbol"] == "AAA" for row in result["allocation"])


def test_no_fabricated_allocation_when_model_is_all_negative() -> None:
    result = plan([stock("MKTX", -11.7)])
    assert not any(row["category"] == "experimental_stock" for row in result["allocation"])
    assert result["combination_analysis"]["stock_positions_selected"] == 0


def test_loss_cap_never_overspends_risky_principal() -> None:
    result = plan([stock("AAA", 35), stock("BBB", 18)], cap=Decimal(100))
    assert Decimal(result["invested_usd"]) <= Decimal(100)
    assert sum(Decimal(row["amount_usd"]) for row in result["allocation"]) == Decimal(2500)
