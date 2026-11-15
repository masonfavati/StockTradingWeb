"""The illustrative budget ledger must never overspend or invent research evidence."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.analysis.budget_planner import BudgetPlanError, make_budget_plan, validate_budget

NOW = datetime(2026, 11, 15, 15, tzinfo=UTC)


def candidate(symbol: str, name: str, price: float = 20) -> dict[str, object]:
    return {
        "symbol": symbol, "name": name, "adjusted_close": price,
        "last_session": "2026-11-13",
    }


IDEAS = [
    candidate("AAA", "AAA Corporation Common Stock"),
    candidate("BBB", "BBB Holdings Ordinary Shares", 40),
]


def plan(
    amount: str = "100", style: str = "balanced", *, opt_in: bool = False,
    scan: str = "complete", candidates: list[dict[str, object]] | None = None,
    completed: datetime | None = None, session: str = "2026-11-13",
) -> dict[str, object]:
    return make_budget_plan(
        Decimal(amount), style,  # type: ignore[arg-type]
        allow_experimental_stocks=opt_in,
        scan_state=scan,
        scan_completed_at=(completed or NOW).isoformat(),
        scan_latest_session=session,
        candidates=IDEAS if candidates is None else candidates,
        now=NOW,
    )


@pytest.mark.parametrize("bad", ["0", "-1", "0.001", "1000000.01", "Infinity", "NaN"])
def test_refuses_invalid_budget(bad: str) -> None:
    with pytest.raises(BudgetPlanError):
        validate_budget(Decimal(bad))


@pytest.mark.parametrize("budget", ["0.01", "0.09", "1", "100", "9999.99"])
def test_every_cent_reconciles(budget: str) -> None:
    for style in ("cautious", "balanced", "growth"):
        result = plan(budget, style, opt_in=True)
        total = sum(Decimal(item["amount_usd"]) for item in result["allocation"])  # type: ignore[index]
        assert total == Decimal(budget)
        assert all(Decimal(item["amount_usd"]) >= 0 for item in result["allocation"])  # type: ignore[index]


def test_default_never_allocates_to_unproven_individual_stocks() -> None:
    result = plan()
    assert [row["symbol"] for row in result["allocation"]] == ["SPY", None]  # type: ignore[index]
    assert result["unallocated_cash_usd"] == "35.00"


def test_explicit_opt_in_caps_each_stock_at_ten_percent() -> None:
    result = plan(opt_in=True)
    assert [row["symbol"] for row in result["allocation"]] == ["SPY", "AAA", "BBB", None]  # type: ignore[index]
    assert [row["amount_usd"] for row in result["allocation"]] == ["65.00", "10.00", "10.00", "15.00"]  # type: ignore[index]
    assert result["illustrative_equity_drop_30pct_usd"] == "25.50"
    assert result["source_session"] == "2026-11-13"


@pytest.mark.parametrize("style", ["balanced", "growth"])
def test_no_usable_scan_moves_experimental_slice_to_cash(style: str) -> None:
    result = plan(style=style, opt_in=True, scan="running")
    assert [row["symbol"] for row in result["allocation"]] == ["SPY", None]  # type: ignore[index]
    assert result["scan_usable_for_ideas"] is False


def test_stale_scan_is_not_used_for_stock_allocation() -> None:
    result = plan(opt_in=True, completed=NOW - timedelta(days=5))
    assert [row["symbol"] for row in result["allocation"]] == ["SPY", None]  # type: ignore[index]


def test_future_dated_scan_is_not_used() -> None:
    result = plan(opt_in=True, completed=NOW + timedelta(minutes=1))
    assert result["scan_usable_for_ideas"] is False


def test_filters_complex_and_unclassified_securities() -> None:
    rows = [
        candidate("WARR", "Example Warrants"),
        candidate("UNIT", "Example Units"),
        candidate("ETF", "Index ETF"),
        candidate("NONE", "Mystery Company"),
        *IDEAS,
    ]
    result = plan(opt_in=True, candidates=rows)
    names = [item["symbol"] for item in result["allocation"]]  # type: ignore[index]
    assert names == ["SPY", "AAA", "BBB", None]


def test_only_one_eligible_stock_never_absorbs_unused_satellite_budget() -> None:
    result = plan(opt_in=True, candidates=[IDEAS[0]])
    assert [row["amount_usd"] for row in result["allocation"]] == ["65.00", "10.00", "25.00"]  # type: ignore[index]


def test_invalid_close_or_mismatched_date_is_skipped() -> None:
    bad = candidate("BAD", "Bad Company Common Stock", 0)
    late = candidate("OLD", "Old Company Common Stock")
    late["last_session"] = "2026-11-12"
    result = plan(opt_in=True, candidates=[bad, late, IDEAS[0]])
    assert [row["symbol"] for row in result["allocation"]] == ["SPY", "AAA", None]  # type: ignore[index]


def test_duplicate_stock_is_never_allocated_twice() -> None:
    result = plan(opt_in=True, candidates=[IDEAS[0], IDEAS[0], IDEAS[1]])
    assert [row["symbol"] for row in result["allocation"]] == ["SPY", "AAA", "BBB", None]  # type: ignore[index]


def test_unknown_style_rejected() -> None:
    with pytest.raises(BudgetPlanError):
        plan(style="gambler")


def test_budget_below_one_cent_stock_slice_stays_in_cash() -> None:
    result = plan("0.01", opt_in=True)
    assert [row["amount_usd"] for row in result["allocation"]] == ["0.00", "0.01"]  # type: ignore[index]


def test_research_share_estimate_is_labeled_as_historical() -> None:
    result = plan(opt_in=True)
    stock = result["allocation"][1]  # type: ignore[index]
    assert stock["indicative_fractional_shares"] == "0.5000"
    assert stock["historical_price_usd"] == "20"
    assert any("NOT executable quotes" in item for item in result["warnings"])  # type: ignore[union-attr]


def test_stale_underlying_market_session_is_not_a_current_stock_quote() -> None:
    result = plan(opt_in=True, session="2026-09-01")
    assert result["scan_usable_for_ideas"] is False
    assert [row["symbol"] for row in result["allocation"]] == ["SPY", None]  # type: ignore[index]
