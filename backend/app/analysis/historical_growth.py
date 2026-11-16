"""Exploratory multi-horizon forecasts using completed daily prices, not scan snapshots.

Deliberately simple nearest-history analogues; every held-out prediction is made
using only outcomes already matured at that time. Retrospective test results are
NOT proof of real-world skill, especially for today's surviving ticker universe.
"""

import math
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise
from statistics import mean
from typing import Any

HORIZONS = {"1m": 20, "3m": 60, "6m": 120}
MIN_WINDOW = 140
MIN_TRAIN = 50
K = 20
MAX_PRICE = 1_000_000_000


class GrowthError(ValueError):
    """Malformed or insufficient historical information."""


@dataclass(frozen=True)
class PricePoint:
    day: date
    close: float


def validate_history(rows: Sequence[PricePoint]) -> list[PricePoint]:
    """Never interpolate missing sessions, duplicate dates, or invalid prices."""
    if len(rows) > 1800:
        raise GrowthError("More than five years of daily prices were returned.")
    sorted_rows = sorted(rows, key=lambda row: row.day)
    if any(not math.isfinite(p.close) or not 0 < p.close < MAX_PRICE for p in sorted_rows):
        raise GrowthError("Unusable stock-price record.")
    if any(a.day >= b.day for a, b in pairwise(sorted_rows)):
        raise GrowthError("Repeated trading dates in historical records.")
    return sorted_rows


def _features(p: Sequence[float], t: int) -> tuple[float, float, float, float]:
    daily = [p[i] / p[i - 1] - 1 for i in range(t - 19, t + 1)]
    average = mean(daily)
    volatility = math.sqrt(mean([(x - average) ** 2 for x in daily]))
    peak = max(p[t - 60 : t + 1])
    return (
        max(-3, min(3, (p[t] / p[t - 20] - 1) / 0.20)),
        max(-3, min(3, (p[t] / p[t - 60] - 1) / 0.40)),
        max(0, min(3, volatility / 0.04)),
        max(-3, min(0, (p[t] / peak - 1) / 0.30)),
    )


def _neighbours(
    p: Sequence[float], *, origin: int, horizon: int,
) -> tuple[float, float, float, float, int, float] | None:
    """Choose analogues whose complete future was known *at origin*."""
    oldest = MIN_WINDOW
    latest_matured = origin - horizon
    origins = range(oldest, latest_matured + 1, 5)
    if len(origins) < MIN_TRAIN:
        return None
    current = _features(p, origin)
    examples: list[tuple[float, float]] = []
    baseline_returns: list[float] = []
    for t in origins:
        target = (p[t + horizon] / p[t] - 1) * 100
        baseline_returns.append(target)
        signal = _features(p, t)
        distance = math.sqrt(sum((a - b) ** 2 for a, b in zip(signal, current, strict=True)))
        examples.append((distance, target))
    examples.sort(key=lambda pair: pair[0])
    selected = [target for _, target in examples[:K]]
    selected.sort()
    # Shrink each pattern-based estimate toward all historically matured outcomes.
    estimate = 0.6 * mean(selected) + 0.4 * mean(baseline_returns)
    low = selected[max(0, int(0.1 * (len(selected) - 1)))]
    high = selected[min(len(selected) - 1, int(0.9 * (len(selected) - 1)))]
    return (estimate, low, high, mean(baseline_returns), len(baseline_returns),
            100 * sum(return_pct > 0 for return_pct in selected) / len(selected))


def _backtest(p: Sequence[float], horizon: int) -> dict[str, Any]:
    # Each evaluation window is disjoint and the model sees ONLY matured targets.
    start = max(MIN_WINDOW + horizon + MIN_TRAIN * 5, int(len(p) * 0.55))
    errors: list[float] = []
    baseline_errors: list[float] = []
    hits = 0
    for origin in range(start, len(p) - horizon, horizon):
        neighbours = _neighbours(p, origin=origin, horizon=horizon)
        if neighbours is None:
            continue
        estimate, _, _, baseline, _, _ = neighbours
        actual = (p[origin + horizon] / p[origin] - 1) * 100
        errors.append(abs(estimate - actual))
        baseline_errors.append(abs(baseline - actual))
        hits += int((estimate > 0) == (actual > 0))
    n = len(errors)
    result: dict[str, Any] = {
        "disjoint_test_windows": n,
        "model_average_error_pp": round(mean(errors), 2) if n else None,
        "baseline_average_error_pp": round(mean(baseline_errors), 2) if n else None,
        "direction_correct_pct": round(100 * hits / n, 1) if n else None,
        "beats_average_baseline": n >= 5 and mean(errors) < mean(baseline_errors) * 0.95,
    }
    return result


def forecast_price_history(rows: Sequence[PricePoint]) -> dict[str, Any]:
    history = validate_history(rows)
    if len(history) < MIN_WINDOW + 20 + MIN_TRAIN * 5:
        return {
            "status": "insufficient_history", "session_count": len(history),
            "as_of": history[-1].day.isoformat() if history else None,
            "current_adjusted_price": round(history[-1].close, 6) if history else None,
            "horizons": {},
        }
    prices = [p.close for p in history]
    forecasts: dict[str, Any] = {}
    for key, horizon in HORIZONS.items():
        analog = _neighbours(prices, origin=len(prices) - 1, horizon=horizon)
        if analog is None:
            continue
        estimate, p10, p90, _, training_examples, positive_share = analog
        tests = _backtest(prices, horizon)
        # Limits are observed historical analogues, NOT statistical confidence bounds.
        low = min(p10, estimate)
        high = max(p90, estimate)
        forecasts[key] = {
            "days": horizon,
            "estimated_change_pct": round(estimate, 2),
            "historical_analogue_low_pct": round(low, 2),
            "historical_analogue_high_pct": round(high, 2),
            "estimated_end_price_usd": round(prices[-1] * max(0, 1 + estimate / 100), 4),
            "analogue_low_price_usd": round(prices[-1] * max(0, 1 + low / 100), 4),
            "analogue_high_price_usd": round(prices[-1] * max(0, 1 + high / 100), 4),
            "matured_training_examples": training_examples,
            "similar_past_patterns_with_gain_pct": round(positive_share, 1),
            "backtest": tests,
            "status": "backtest_candidate" if tests["beats_average_baseline"] else "unvalidated",
        }
    return {
        "status": "exploratory_estimates" if forecasts else "insufficient_history",
        "session_count": len(history),
        "as_of": history[-1].day.isoformat(),
        "current_adjusted_price": round(prices[-1], 6),
        "horizons": forecasts,
        "disclaimer": (
            "Estimates are experimental historical analogues, not reliable forecasts or buy signals. "
            "Backtests use only today's surviving selected tickers and prices adjusted using "
            "corporate actions known now, so historical selection and corporate-action bias remain. "
            "A low/high analogue range is NOT a guaranteed or calibrated confidence interval. "
            "No reliable real-time sell timing is possible."
        ),
    }


def daily_correlation(a: Sequence[PricePoint], b: Sequence[PricePoint]) -> float | None:
    """Measure trailing price changes on matched actual trading days only."""
    left = {p.day: p.close for p in validate_history(a)}
    right = {p.day: p.close for p in validate_history(b)}
    common = sorted(set(left) & set(right))[-90:]
    if len(common) < 45:
        return None
    x = [left[d] / left[before] - 1 for before, d in pairwise(common)]
    y = [right[d] / right[before] - 1 for before, d in pairwise(common)]
    avg_x, avg_y = mean(x), mean(y)
    numerator = sum((i - avg_x) * (j - avg_y) for i, j in zip(x, y, strict=True))
    denom = math.sqrt(sum((i - avg_x) ** 2 for i in x) * sum((j - avg_y) ** 2 for j in y))
    return round(numerator / denom, 3) if denom > 1e-12 else None


def compare_forecasts(
    forecasts: Mapping[str, Mapping[str, Any]], horizon: str,
    stock_histories: Mapping[str, Sequence[PricePoint]],
) -> list[dict[str, Any]]:
    """Rank current scanned symbols only; never imply an entire-market forecast."""
    rows: list[dict[str, Any]] = []
    for symbol, result in forecasts.items():
        f = result.get("horizons", {}).get(horizon)
        if not isinstance(f, dict):
            continue
        rows.append({
            "symbol": symbol,
            "estimated_change_pct": f["estimated_change_pct"],
            "historical_analogue_low_pct": f["historical_analogue_low_pct"],
            "historical_analogue_high_pct": f["historical_analogue_high_pct"],
            "current_adjusted_price": result["current_adjusted_price"],
            "estimated_end_price_usd": f["estimated_end_price_usd"],
            "analogue_low_price_usd": f["analogue_low_price_usd"],
            "analogue_high_price_usd": f["analogue_high_price_usd"],
            "status": f["status"],
            "backtest": f["backtest"],
            "history_sessions": len(stock_histories[symbol]),
            "similar_past_patterns_with_gain_pct": f["similar_past_patterns_with_gain_pct"],
            "as_of": result["as_of"],
        })
    return sorted(rows, key=lambda row: (-row["estimated_change_pct"], row["symbol"]))
