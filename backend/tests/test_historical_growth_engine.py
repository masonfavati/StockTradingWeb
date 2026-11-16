"""Pure, deterministic validation: history cannot leak future target observations."""

import math
from datetime import date, timedelta

import pytest

from app.analysis.historical_growth import (
    GrowthError,
    PricePoint,
    _neighbours,
    daily_correlation,
    forecast_price_history,
    validate_history,
)


def make_history(n: int = 1250, *, rising: bool = True) -> list[PricePoint]:
    return [PricePoint(date(2020, 1, 1) + timedelta(days=i),
                       100 * (1.0002 ** i) * (1 + 0.02 * math.sin(i / 18))
                       if rising else 100 * (1.0001 ** i) * (1 + 0.03 * math.cos(i / 23)))
            for i in range(n)]


def test_history_rejects_duplicate_or_invalid_price() -> None:
    same_day = date(2026, 1, 1)
    with pytest.raises(GrowthError, match="Repeated"):
        validate_history([PricePoint(same_day, 1), PricePoint(same_day, 2)])
    with pytest.raises(GrowthError, match="Unusable"):
        validate_history([PricePoint(same_day, float("nan"))])


def test_short_history_does_not_invent_estimate() -> None:
    result = forecast_price_history(make_history(100))
    assert result["status"] == "insufficient_history"
    assert result["horizons"] == {}


def test_forecast_horizons_and_backtests_are_labeled_historical() -> None:
    result = forecast_price_history(make_history())
    assert result["status"] == "exploratory_estimates"
    assert set(result["horizons"]) == {"1m", "3m", "6m"}
    for row in result["horizons"].values():
        assert row["status"] in ("unvalidated", "backtest_candidate")
        assert row["historical_analogue_low_pct"] <= row["estimated_change_pct"]
        assert row["estimated_change_pct"] <= row["historical_analogue_high_pct"]
        assert row["backtest"]["disjoint_test_windows"] > 0


def test_past_origin_estimate_cannot_see_maturing_future_returns() -> None:
    p = [entry.close for entry in make_history(1000)]
    origin = 800
    estimate = _neighbours(p, origin=origin, horizon=60)
    changed = p.copy()
    for day in range(origin + 1, len(changed)):
        changed[day] *= 200
    assert _neighbours(changed, origin=origin, horizon=60) == estimate


def test_correlation_only_matches_observed_dates() -> None:
    first = make_history(200)
    second = [PricePoint(row.day, row.close * 2) for row in first]
    assert daily_correlation(first, second) == 1.0
    assert daily_correlation(first, second[:20]) is None
