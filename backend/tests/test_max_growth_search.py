"""The highest-model-gain view is exhaustive *within the screened universe*."""

from datetime import date, timedelta
from decimal import Decimal
from math import comb

import pytest

from app.analysis.historical_growth import PricePoint
from app.analysis.max_growth_search import _fill_optimal_cents, build_max_model_growth_plan


def prices() -> list[PricePoint]:
    return [PricePoint(date(2023, 1, 1) + timedelta(days=i), 100.0 + 0.1 * i)
            for i in range(500)]


def idea(symbol: str, change: float) -> dict:
    return {
        "symbol": symbol, "estimated_change_pct": change,
        "historical_analogue_low_pct": -10.0,
        "historical_analogue_high_pct": max(change, 20),
        "backtest": {},
    }


def choose(
    ranked: list[dict], *, spy_change: float = 3.0,
    cap: Decimal | None = None, allow: bool = True,
) -> dict:
    return build_max_model_growth_plan(
        Decimal(2500), style="balanced", horizon="long", max_loss_usd=cap,
        allow_exploratory=allow,
        ranked=ranked,
        histories={"SPY": prices(), **{row["symbol"]: prices() for row in ranked}},
        benchmark={"horizons": {"6m": {"estimated_change_pct": spy_change}}},
    )


def test_searches_entire_twenty_stock_forecast_pool_without_top_twelve_cutoff(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.analysis.max_growth_search.daily_correlation", lambda *_: 0.1)
    ranked = [idea(f"A{i:02d}", 12.0) for i in range(19)] + [idea("Z20", 120.0)]
    result = choose(ranked, spy_change=0.5)
    search = result["combination_analysis"]
    subset_count = sum(comb(20, size) for size in range(1, 5))
    assert search["combinations_considered"] == 2 * subset_count + 1
    assert search["risk_eligible_stocks"] == 20
    assert any(row["symbol"] == "Z20" for row in result["allocation"])
    assert Decimal(search["illustrative_model_gain_usd"]) > 300
    assert sum(Decimal(row["amount_usd"]) for row in result["allocation"]) == Decimal(2500)


def test_max_gain_chooses_stock_only_when_spy_is_weak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.analysis.max_growth_search.daily_correlation", lambda *_: 0.2)
    ranked = [idea(s, v) for s, v in zip("ABCD", (40, 35, 30, 25), strict=True)]
    result = choose(ranked, spy_change=0.2)
    assert result["combination_analysis"]["winning_structure"] == "stocks_and_cash"
    assert not any(row["symbol"] == "SPY" for row in result["allocation"])
    assert len([row for row in result["allocation"] if row["category"] == "experimental_stock"]) == 4
    assert result["combination_analysis"]["illustrative_model_gain_usd"] == "325.00"


def test_max_gain_chooses_spy_plus_stocks_when_spy_adds_more_gain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.analysis.max_growth_search.daily_correlation", lambda *_: 0.2)
    result = choose([idea("AAA", 35), idea("BBB", 18)], spy_change=6)
    assert result["combination_analysis"]["winning_structure"] == "spy_and_stocks"
    assert {row["symbol"] for row in result["allocation"]} == {"AAA", "BBB", "SPY", None}
    assert result["combination_analysis"]["illustrative_model_gain_usd"] == "215.00"
    assert next(row["amount_usd"] for row in result["allocation"] if row["symbol"] == "SPY") == "1375.00"


def test_negative_estimates_cannot_receive_allocation() -> None:
    result = choose([idea("MKTX", -11.7), idea("AAA", 12)], spy_change=-2)
    assert result["combination_analysis"]["winning_structure"] == "stocks_and_cash"
    assert not any(row["symbol"] in ("MKTX", "SPY") for row in result["allocation"])
    assert any(row["symbol"] == "MKTX" and "not positive" in row["reason"] for row in result["declined"])


def test_risky_money_is_bounded_by_affordable_loss_budget() -> None:
    result = choose([idea("AAA", 40), idea("BBB", 30)], spy_change=20, cap=Decimal(100))
    assert Decimal(result["invested_usd"]) <= Decimal(100)
    assert Decimal(result["cash_usd"]) >= Decimal(2400)
    assert sum(Decimal(row["amount_usd"]) for row in result["allocation"]) == Decimal(2500)
    assert all(Decimal(row["amount_usd"]) <= Decimal(250) for row in result["allocation"]
               if row["category"] == "experimental_stock")


def test_opt_out_and_unverified_manual_stocks_cannot_produce_optimized_picks() -> None:
    result = choose([idea("AAA", 40)], allow=False)
    assert result["cash_usd"] == "2500.00"
    assert result["combination_analysis"]["combinations_considered"] == 0
    assert all(row["category"] == "cash" for row in result["allocation"])


def test_missing_correlations_fail_closed_without_skipping_subset_accounting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr("app.analysis.max_growth_search.daily_correlation", lambda *_: None)
    result = choose([idea("AAA", 45), idea("BBB", 44)])
    assert result["combination_analysis"]["correlation_rejected"] == 2
    assert sum(row["category"] == "experimental_stock" for row in result["allocation"]) <= 1


def test_cannot_claim_unbounded_stock_forecast_universe() -> None:
    ranked = [idea(f"A{i:02d}", 10) for i in range(21)]
    with pytest.raises(ValueError, match="up to 20"):
        choose(ranked)


def test_exact_cent_allocation_matches_brute_force_on_tiny_budget() -> None:
    """Demonstrate exact dollar optimization, not a few guessed weight splits."""
    pair = [idea("AAA", 35), idea("BBB", 25)]
    result = _fill_optimal_cents(
        pair, include_spy=True, total_cents=100, risky_cap_cents=30,
        stock_sleeve_cents=20, core_cap_cents=55, spy_estimate=Decimal(20),
    )
    assert result is not None
    _, exact_gain = result
    brute = max(
        Decimal(a * 35 + b * 25 + spy * 20) / Decimal(10_000)
        for a in range(1, 11)
        for b in range(1, 11)
        for spy in range(56)
        if a + b <= 20 and a + b + spy <= 30
    )
    assert exact_gain == brute
