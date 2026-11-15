"""Historical diversification evidence is bounded, aligned and never imputed."""

import math
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any

import pytest

from app.analysis.budget_planner import make_budget_plan
from app.analysis.portfolio_comovement import (
    analyze_historical_comovement,
    unavailable_review,
)
from app.market_data.history_client import DailyBar

SESSION = date(2026, 11, 13)
START = SESSION - timedelta(days=87)
DATES = [START + timedelta(days=i) for i in range(88)
         if (START + timedelta(days=i)).weekday() < 5][-61:]
assert len(DATES) == 61


def fake_bar(symbol: str, date_: date, close: float) -> DailyBar:
    price = Decimal(str(close))
    return DailyBar(
        symbol=symbol, session_date=date_,
        bar_timestamp=datetime.combine(date_, datetime.min.time(), tzinfo=UTC),
        open_price=price, high_price=price, low_price=price,
        close_price=price, volume=10_000, trade_count=10, vwap=None,
    )


class Provider:
    def __init__(self, *, missing: tuple[str, date] | None = None, duplicate: bool = False,
                 future: bool = False, incomplete_spy: bool = False) -> None:
        self.calls: list[dict[str, Any]] = []
        prices = {
            "SPY": [100 + (0.45 * i) + math.sin(i * 0.47) for i in range(61)],
            "AAA": [20 + (0.18 * i) + 0.4 * math.sin(i * 0.47) for i in range(61)],
            "BBB": [40 + (0.36 * i) + 0.8 * math.sin(i * 0.47) for i in range(61)],
            "CCC": [25 + 0.03 * i + 2.0 * math.sin(i * 1.77) for i in range(61)],
        }
        self.bars = [fake_bar(symbol, date_, prices[symbol][i])
                     for symbol in prices for i, date_ in enumerate(DATES)
                     if (symbol, date_) != missing]
        if incomplete_spy:
            self.bars = [b for b in self.bars if b.symbol != "SPY" or b.session_date != DATES[-1]]
        if duplicate:
            self.bars.append(self.bars[0])
        if future:
            self.bars.append(fake_bar("SPY", SESSION + timedelta(days=1), 110))

    def pages(self, symbols: list[str], *, start: date, end: date,
              feed: str, adjustment: str, page_limit: int) -> Any:
        self.calls.append({"symbols": symbols, "start": start, "end": end,
                           "feed": feed, "adjustment": adjustment, "limit": page_limit})
        yield [bar for bar in self.bars if bar.symbol in symbols]


def run(provider: Provider, symbols: tuple[str, ...] = ("AAA", "BBB")) -> dict[str, Any]:
    return analyze_historical_comovement(
        provider, signal_session=SESSION,
        stock_amounts_usd={symbol: Decimal(10) for symbol in symbols},
        core_amount_usd=Decimal(65), budget_usd=Decimal(100),
    )


def test_pair_correlation_excludes_second_when_near_identical() -> None:
    provider = Provider()
    result = run(provider)
    assert result["status"] == "checked"
    assert result["approved_symbols"] == ["AAA"]
    assert result["excluded"] == [{"symbol": "BBB", "reason": "high_positive_correlation"}]
    assert result["pairwise_correlations"][0]["paired_returns"] == 60
    assert result["pairwise_correlations"][0]["correlation"] > 0.8
    assert result["portfolio_annualized_historical_volatility_pct"] > 0
    assert result["portfolio_historical_max_drawdown_pct"] <= 0
    assert provider.calls[0]["symbols"] == ["SPY", "AAA", "BBB"]
    assert provider.calls[0]["adjustment"] == "all"
    assert provider.calls[0]["feed"] == "sip"
    assert provider.calls[0]["end"] == SESSION + timedelta(days=1)


def test_non_correlated_stock_pair_can_be_retained() -> None:
    result = run(Provider(), ("AAA", "CCC"))
    assert result["approved_symbols"] == ["AAA", "CCC"]
    assert result["excluded"] == []
    assert result["pairwise_correlations"][0]["correlation"] < 0.8
    assert all(x["paired_returns"] == 60 for x in result["spy_correlations"])


def test_missing_one_day_never_interpolates_or_substitutes() -> None:
    result = run(Provider(missing=("BBB", DATES[10])))
    assert result["approved_symbols"] == ["AAA"]
    assert result["excluded"] == [{"symbol": "BBB", "reason": "insufficient_aligned_sessions"}]


def test_missing_last_spy_session_rejects_all_stocks() -> None:
    result = run(Provider(incomplete_spy=True))
    assert result["status"] == "insufficient_history"
    assert result["approved_symbols"] == []


@pytest.mark.parametrize("kwargs", [{"duplicate": True}, {"future": True}])
def test_duplicate_or_future_daily_bar_never_accepted(kwargs: dict[str, bool]) -> None:
    with pytest.raises(ValueError):
        run(Provider(**kwargs))  # type: ignore[arg-type]


def test_no_stock_candidates_makes_zero_provider_requests() -> None:
    provider = Provider()
    result = run(provider, ())
    assert result["status"] == "not_applicable"
    assert provider.calls == []


def test_limit_provider_requests_to_two_stock_ideas_and_one_reference() -> None:
    provider = Provider()
    with pytest.raises(ValueError):
        run(provider, ("AAA", "BBB", "CCC"))
    assert provider.calls == []


def test_cash_and_principal_risk_cap_hold_when_one_correlated_stock_dropped() -> None:
    review = run(Provider())
    ideas = [
        {"symbol": symbol, "name": f"{symbol} Corporation Common Stock",
         "adjusted_close": 20.0, "last_session": SESSION.isoformat(),
         "annualized_volatility_pct": 30.0, "drawdown_60d_pct": -8.0,
         "approx_daily_dollar_volume": 12_000_000.0}
        for symbol in ("AAA", "BBB")
    ]
    result = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        scan_state="complete", scan_completed_at="2026-11-14T21:00:00+00:00",
        scan_latest_session=SESSION.isoformat(), candidates=ideas,
        require_historical_comovement=True, comovement_review=review,
        now=datetime(2026, 11, 15, 2, tzinfo=UTC),
    )
    assert [row["amount_usd"] for row in result["allocation"]] == ["65.00", "10.00", "25.00"]
    assert result["quality_review"]["correlation_gated_count"] == 1
    assert result["unallocated_cash_usd"] == "25.00"
    assert result["comovement_review"]["status"] == "checked"


def test_unavailable_evidence_keeps_all_experimental_money_in_cash() -> None:
    plan = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        scan_state="complete", scan_completed_at="2026-11-14T21:00:00+00:00",
        scan_latest_session=SESSION.isoformat(), candidates=[{
            "symbol": "AAA", "name": "AAA Corporation Common Stock",
            "adjusted_close": 20.0, "last_session": SESSION.isoformat(),
            "annualized_volatility_pct": 30.0, "drawdown_60d_pct": -8.0,
            "approx_daily_dollar_volume": 12_000_000.0,
        }],
        require_historical_comovement=True,
        comovement_review=unavailable_review(["AAA"]),
        now=datetime(2026, 11, 15, 2, tzinfo=UTC),
    )
    assert [row["amount_usd"] for row in plan["allocation"]] == ["65.00", "35.00"]
    assert plan["quality_review"]["correlation_gated_count"] == 1


def test_legacy_plan_does_not_invoke_new_evidence_gates() -> None:
    plan = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=False,
        scan_state="idle", scan_completed_at=None, scan_latest_session=None,
        candidates=[],
    )
    assert plan["comovement_review"] is None
    assert plan["historical_comovement_required"] is False


def test_loss_cap_does_not_reweight_surviving_stock_after_correlation_exclusion() -> None:
    review = analyze_historical_comovement(
        Provider(), signal_session=SESSION,
        stock_amounts_usd={"AAA": Decimal("2.50"), "BBB": Decimal("2.50")},
        core_amount_usd=Decimal(65), budget_usd=Decimal(100),
    )
    ideas = [{
        "symbol": sym, "name": f"{sym} Corporation Common Stock",
        "adjusted_close": 20.0, "last_session": SESSION.isoformat(),
        "annualized_volatility_pct": 30.0, "drawdown_60d_pct": -8.0,
        "approx_daily_dollar_volume": 12_000_000.0,
    } for sym in ("AAA", "BBB")]
    plan = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        max_loss_usd=Decimal(70),
        scan_state="complete", scan_completed_at="2026-11-14T21:00:00+00:00",
        scan_latest_session=SESSION.isoformat(), candidates=ideas,
        require_historical_comovement=True, comovement_review=review,
        now=datetime(2026, 11, 15, 2, tzinfo=UTC),
    )
    assert [r["amount_usd"] for r in plan["allocation"]] == ["65.00", "2.50", "32.50"]
    assert plan["modeled_risky_principal_usd"] == "67.50"


def test_invalid_symbol_is_rejected_before_provider_request() -> None:
    provider = Provider()
    with pytest.raises(ValueError):
        run(provider, ("AAA,BBB",))
    assert provider.calls == []
