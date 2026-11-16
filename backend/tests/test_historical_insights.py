"""Descriptive chart summaries must use real chart dates, never guessed prices."""

from datetime import date

from app.analysis.historical_insights import describe_price_history


def series(*prices: float) -> list[tuple[date, float]]:
    return [(date(2026, 11, day + 1), price) for day, price in enumerate(prices)]


def test_high_low_drop_and_daily_changes_use_actual_observations() -> None:
    result = describe_price_history(series(100, 120, 90, 110))
    assert result["highest_price_usd"] == 120
    assert result["highest_date"] == "2026-11-02"
    assert result["lowest_price_usd"] == 90
    assert result["lowest_date"] == "2026-11-03"
    assert result["largest_drop_from_previous_high_pct"] == 25
    assert result["drop_high_date"] == "2026-11-02"
    assert result["drop_low_date"] == "2026-11-03"
    assert result["average_change_between_recorded_days_pct"] == 22.41
    assert (result["up_days"], result["down_days"], result["flat_days"]) == (2, 1, 0)


def test_empty_and_single_day_do_not_claim_changes() -> None:
    empty = describe_price_history([])
    assert empty["largest_drop_from_previous_high_pct"] is None
    assert empty["average_change_between_recorded_days_pct"] is None
    single = describe_price_history(series(102))
    assert single["highest_price_usd"] == 102
    assert single["largest_drop_from_previous_high_pct"] is None


def test_rising_history_reports_zero_decline() -> None:
    result = describe_price_history(series(100, 101, 102))
    assert result["largest_drop_from_previous_high_pct"] == 0
    assert result["up_days"] == 2


def test_spy_comparison_only_uses_exact_matching_days() -> None:
    observations = series(100, 120, 110)
    benchmark = series(100, 110, 120)
    result = describe_price_history(observations, spy_observations=benchmark)
    assert result["spy_change_pct"] == 20
    assert result["difference_vs_spy_percentage_points"] == -10
    unmatched = [(date(2026, 11, 2), 100.0), (date(2026, 11, 3), 110.0)]
    result = describe_price_history(observations, spy_observations=unmatched)
    assert result["spy_change_pct"] is None
    assert result["difference_vs_spy_percentage_points"] is None


def test_flat_prices_remain_flat() -> None:
    result = describe_price_history(series(40, 40, 40))
    assert result["flat_days"] == 2
    assert result["average_change_between_recorded_days_pct"] == 0
    assert result["largest_drop_from_previous_high_pct"] == 0
