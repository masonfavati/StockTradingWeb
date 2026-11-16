"""Descriptive, hindsight-only price summaries for a chart's actual displayed dates.

Not a forecast, trading signal, risk limit, or a point-in-time backtest.
"""

from collections.abc import Sequence
from datetime import date
from typing import Any


def describe_price_history(
    observations: Sequence[tuple[date, float]],
    *, spy_observations: Sequence[tuple[date, float]] = (),
) -> dict[str, Any]:
    """Analyze only sorted, nonmissing daily adjusted closes already shown by the chart.

    The caller validates prices and dates. The SPY comparison uses the same
    first/last actual sessions and never fills in absent values.
    """
    if not observations:
        return {
            "highest_price_usd": None, "highest_date": None,
            "lowest_price_usd": None, "lowest_date": None,
            "largest_drop_from_previous_high_pct": None,
            "drop_high_date": None, "drop_low_date": None,
            "average_change_between_recorded_days_pct": None,
            "up_days": 0, "down_days": 0, "flat_days": 0,
            "spy_change_pct": None, "difference_vs_spy_percentage_points": None,
        }

    high_day, high = max(observations, key=lambda item: item[1])
    low_day, low = min(observations, key=lambda item: item[1])
    peak_date, peak = observations[0]
    worst_drop = 0.0
    worst_peak = peak_date
    worst_bottom = peak_date
    abs_changes: list[float] = []
    up = down = flat = 0
    for index, (day, price) in enumerate(observations):
        if price > peak:
            peak, peak_date = price, day
        decline = (peak - price) / peak * 100
        if decline > worst_drop:
            worst_drop = decline
            worst_peak, worst_bottom = peak_date, day
        if index > 0:
            previous = observations[index - 1][1]
            change = (price / previous - 1) * 100
            abs_changes.append(abs(change))
            if change > 0:
                up += 1
            elif change < 0:
                down += 1
            else:
                flat += 1

    spy_change: float | None = None
    excess: float | None = None
    if len(spy_observations) >= 2 and len(spy_observations) == len(observations):
        aligned = all(a[0] == b[0] for a, b in zip(observations, spy_observations, strict=True))
        if aligned:
            spy_change = (spy_observations[-1][1] / spy_observations[0][1] - 1) * 100
            stock_change = (observations[-1][1] / observations[0][1] - 1) * 100
            excess = stock_change - spy_change

    return {
        "highest_price_usd": round(high, 8), "highest_date": high_day.isoformat(),
        "lowest_price_usd": round(low, 8), "lowest_date": low_day.isoformat(),
        "largest_drop_from_previous_high_pct": round(worst_drop, 2) if abs_changes else None,
        "drop_high_date": worst_peak.isoformat() if abs_changes else None,
        "drop_low_date": worst_bottom.isoformat() if abs_changes else None,
        "average_change_between_recorded_days_pct": round(
            sum(abs_changes) / len(abs_changes), 2,
        ) if abs_changes else None,
        "up_days": up, "down_days": down, "flat_days": flat,
        "spy_change_pct": round(spy_change, 2) if spy_change is not None else None,
        "difference_vs_spy_percentage_points": round(excess, 2) if excess is not None else None,
    }
