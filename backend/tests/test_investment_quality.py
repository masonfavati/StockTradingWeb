"""Historical quality gates are explicit, conservative, and never forecast returns."""

from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.analysis.budget_planner import make_budget_plan
from app.analysis.investment_quality import screen_budget_candidates

NOW = datetime(2026, 11, 15, 15, tzinfo=UTC)


def row(symbol: str, name: str | None = None, **updates: object) -> dict[str, object]:
    result: dict[str, object] = {
        "symbol": symbol,
        "name": name or f"{symbol} Incorporated Common Stock",
        "last_session": "2026-11-13",
        "adjusted_close": 25.0,
        "annualized_volatility_pct": 40.0,
        "drawdown_60d_pct": -8.0,
        "approx_daily_dollar_volume": 12_000_000.0,
    }
    result.update(updates)
    return result


def plan(candidates: list[dict[str, object]], *, loss: str | None = None) -> dict[str, object]:
    return make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        max_loss_usd=Decimal(loss) if loss is not None else None,
        scan_state="complete", scan_completed_at=NOW.isoformat(),
        scan_latest_session="2026-11-13", candidates=candidates, now=NOW,
    )


def symbols(result: dict[str, object]) -> list[str | None]:
    return [item["symbol"] for item in result["allocation"]]  # type: ignore[index]


def test_two_good_different_issuers_keep_previous_illustrative_split() -> None:
    result = plan([row("AAA"), row("BBB")])
    assert symbols(result) == ["SPY", "AAA", "BBB", None]
    assert [item["amount_usd"] for item in result["allocation"]] == [  # type: ignore[index]
        "65.00", "10.00", "10.00", "15.00",
    ]
    assert result["quality_review"]["selected_count"] == 2  # type: ignore[index]
    assert "dollar volume" in result["allocation"][1]["reason"]  # type: ignore[index]


@pytest.mark.parametrize(("updates", "reason"), [
    ({"adjusted_close": 4.99}, "below_price_floor"),
    ({"approx_daily_dollar_volume": 4_999_999.99}, "below_liquidity_screen"),
    ({"annualized_volatility_pct": 80.01}, "above_volatility_screen"),
    ({"annualized_volatility_pct": 0}, "above_volatility_screen"),
    ({"drawdown_60d_pct": -25.01}, "outside_drawdown_screen"),
    ({"drawdown_60d_pct": 1}, "outside_drawdown_screen"),
    ({"approx_daily_dollar_volume": None}, "missing_or_invalid_metrics"),
    ({"annualized_volatility_pct": float("nan")}, "missing_or_invalid_metrics"),
    ({"adjusted_close": True}, "missing_or_invalid_metrics"),
    ({"drawdown_60d_pct": "-3"}, "missing_or_invalid_metrics"),
    ({"adjusted_close": 10**500}, "missing_or_invalid_metrics"),
])
def test_rejects_unsafe_or_missing_evidence(updates: dict[str, object], reason: str) -> None:
    selected, audit = screen_budget_candidates([row("AAA", **updates)], "2026-11-13")
    assert selected == []
    assert audit["excluded_counts"] == {reason: 1}


@pytest.mark.parametrize("updates", [
    {"adjusted_close": 5.0},
    {"approx_daily_dollar_volume": 5_000_000.0},
    {"annualized_volatility_pct": 80.0},
    {"drawdown_60d_pct": -25.0},
])
def test_boundary_values_are_explicit_and_inclusive(updates: dict[str, object]) -> None:
    selected, report = screen_budget_candidates([row("AAA", **updates)], "2026-11-13")
    assert len(selected) == 1
    assert report["selected_count"] == 1


def test_different_share_classes_same_apparent_issuer_not_both_allocated() -> None:
    candidates = [
        row("ABC.A", "Example Holdings Class A Common Stock"),
        row("ABC.B", "Example Holdings Class B Common Stock"),
        row("ZZZ"),
    ]
    result = plan(candidates)
    assert symbols(result) == ["SPY", "ABC.A", "ZZZ", None]
    assert result["quality_review"]["excluded_counts"]["repeated_apparent_issuer"] == 1  # type: ignore[index]


def test_extra_stock_is_excluded_not_allocated() -> None:
    result = plan([row("AAA"), row("BBB"), row("CCC")])
    assert symbols(result) == ["SPY", "AAA", "BBB", None]
    assert result["quality_review"]["excluded_counts"]["passed_not_selected"] == 1  # type: ignore[index]


def test_no_evidence_never_forces_experimental_allocation() -> None:
    result = plan([row("AAA", annualized_volatility_pct=None)])
    assert symbols(result) == ["SPY", None]
    assert result["unallocated_cash_usd"] == "35.00"
    assert result["quality_review"]["selected_count"] == 0  # type: ignore[index]


def test_quality_screen_does_not_override_personal_loss_budget() -> None:
    result = plan([row("AAA"), row("BBB")], loss="70")
    assert [item["amount_usd"] for item in result["allocation"]] == [  # type: ignore[index]
        "65.00", "2.50", "2.50", "30.00",
    ]
    assert result["modeled_risky_principal_usd"] == "70.00"


def test_outdated_session_and_duplicate_ticker_are_reported() -> None:
    selected, report = screen_budget_candidates(
        [row("AAA"), row("AAA"), row("OLD", last_session="2026-11-12")],
        "2026-11-13",
    )
    assert [x["symbol"] for x in selected] == ["AAA"]
    assert report["excluded_counts"]["duplicate_ticker"] == 1
    assert report["excluded_counts"]["outdated_session"] == 1


def test_complex_names_and_unclassified_names_are_blocked() -> None:
    candidates = [
        row("AAA", "Something Warrants"),
        row("BBB", "An ETF Fund"),
        row("CCC", "Mystery Corp"),
        row("DDD"),
    ]
    selected, report = screen_budget_candidates(candidates, "2026-11-13")
    assert [x["symbol"] for x in selected] == ["DDD"]
    assert report["excluded_counts"]["unverified_share_type"] == 3


def test_no_metric_imputation_and_no_provider_calls() -> None:
    selected, report = screen_budget_candidates([{"symbol": "AAA", "name": "AAA Common Stock", "last_session": "2026-11-13"}], "2026-11-13")
    assert selected == []
    assert report["excluded_counts"] == {"missing_or_invalid_metrics": 1}
