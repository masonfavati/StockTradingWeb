"""Cents-exact, risk-aware *exploratory* investment-basket illustrations.

Neither past-pattern estimates nor correlation establish the most profitable
future investment. No trades are placed, and risky principal can be lost.
"""

import math
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations
from typing import Any, Literal

from app.analysis.budget_planner import validate_budget, validate_max_loss
from app.analysis.historical_growth import PricePoint, daily_correlation

HORIZON_TO_FORECAST = {"short": "1m", "medium": "3m", "long": "6m"}
CORE_PCT: dict[str, dict[str, int]] = {
    "short": {"cautious": 0, "balanced": 0, "growth": 0},
    "medium": {"cautious": 20, "balanced": 25, "growth": 30},
    "long": {"cautious": 50, "balanced": 55, "growth": 60},
}
STOCK_PCT: dict[str, dict[str, int]] = {
    "short": {"cautious": 0, "balanced": 0, "growth": 0},
    "medium": {"cautious": 0, "balanced": 10, "growth": 15},
    "long": {"cautious": 10, "balanced": 20, "growth": 30},
}
MAX_STOCK_PCT = 10
MAX_BASKET_STOCKS = 4
MAX_COMBINATION_CANDIDATES = 12


def _usd(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def _spread_stock_budget(
    scores: Sequence[float], *, stock_cents: int, total_cents: int,
) -> list[int] | None:
    """Allocate more to stronger *risk-adjusted* scores, ≤10% per stock.

    Use cent-exact integer arithmetic; leave unreachable or unapproved money
    as cash instead of using it to enlarge one concentrated position.
    """
    if not scores or any(not math.isfinite(score) or score <= 0 for score in scores):
        return None
    each_cap = total_cents * MAX_STOCK_PCT // 100
    minimum = max(1, total_cents // 100)  # at least ~1% to show a position
    used = min(stock_cents, each_cap * len(scores))
    if each_cap < minimum or used < minimum * len(scores):
        return None
    weights = [minimum] * len(scores)
    remaining = used - sum(weights)
    # Water-fill positive scores with capped allocations; each iteration
    # distributes a substantial chunk until the last handful of pennies.
    while remaining:
        active = [index for index, weight in enumerate(weights) if weight < each_cap]
        if not active:
            break
        total_score = sum(scores[index] for index in active)
        distributed = 0
        for index in active:
            share = max(1, int(remaining * scores[index] / total_score))
            share = min(share, each_cap - weights[index], remaining - distributed)
            if share <= 0:
                continue
            weights[index] += share
            distributed += share
            if distributed == remaining:
                break
        if distributed == 0:
            break
        remaining -= distributed
    return weights


def _basket_choice(
    candidates: Sequence[Mapping[str, Any]],
    scores: Mapping[str, float],
    histories: Mapping[str, Sequence[PricePoint]],
    *, budget_cents: int, stock_cents: int,
) -> tuple[list[tuple[Mapping[str, Any], int]], int]:
    """Search bounded subsets using risk-adjusted *dollar* opportunity.

    This is a transparent heuristic, not a calibrated probability optimizer.
    A single large prediction cannot consume the portfolio; matched-date
    co-movement and per-stock concentration limits constrain the baskets.
    """
    top = sorted(candidates, key=lambda row: (-scores[str(row["symbol"])], str(row["symbol"])))
    top = top[:MAX_COMBINATION_CANDIDATES]
    correlations: dict[tuple[str, str], float | None] = {}
    for first, second in combinations(top, 2):
        a, b = sorted((str(first["symbol"]), str(second["symbol"])))
        correlations[(a, b)] = daily_correlation(histories[a], histories[b])
    best_utility = 0.0
    best: list[tuple[Mapping[str, Any], int]] = []
    checked = 0
    for size in range(1, min(MAX_BASKET_STOCKS, len(top)) + 1):
        for subset in combinations(top, size):
            checked += 1
            paired: list[tuple[int, int, float]] = []
            valid = True
            for i, j in combinations(range(size), 2):
                a, b = sorted((str(subset[i]["symbol"]), str(subset[j]["symbol"])))
                corr = correlations[(a, b)]
                if corr is None or corr >= 0.80:
                    valid = False
                    break
                paired.append((i, j, corr))
            if not valid:
                continue
            amounts = _spread_stock_budget(
                [scores[str(row["symbol"])] for row in subset],
                stock_cents=stock_cents, total_cents=budget_cents,
            )
            if amounts is None:
                continue
            # Amount in cents × a heuristic, percent-point expected advantage.
            # Penalize concentrated allocations and strongly correlated pairs.
            utility = sum(
                amount * scores[str(row["symbol"])]
                for row, amount in zip(subset, amounts, strict=True)
            )
            utility -= 2.0 * sum(
                max(0.0, corr - 0.25) * min(amounts[i], amounts[j])
                for i, j, corr in paired
            )
            utility -= 2.0 * sum(amount * amount / budget_cents for amount in amounts)
            if utility > best_utility + 1e-7:
                best_utility = utility
                best = list(zip(subset, amounts, strict=True))
    return best, checked


def screen_ranked_stock_candidates(
    ranked: Sequence[Mapping[str, Any]],
    histories: Mapping[str, Sequence[PricePoint]],
) -> tuple[list[Mapping[str, Any]], dict[str, float], list[dict[str, str]], int]:
    """Exactly the same evidence gates for the ordinary and maximum-gain views.

    The estimated growth is not a calibrated probability. A passing stock
    can still lose money; the gates deliberately do not invent extra picks.
    """
    reviewed: list[Mapping[str, Any]] = []
    scores: dict[str, float] = {}
    declined: list[dict[str, str]] = []
    positive_count = 0
    for item in ranked:
        symbol = str(item["symbol"])
        estimate = float(item["estimated_change_pct"])
        lower = float(item["historical_analogue_low_pct"])
        upper = float(item["historical_analogue_high_pct"])
        if not all(math.isfinite(value) for value in (estimate, lower, upper)):
            declined.append({"symbol": symbol, "reason": "Unusable historical growth or risk estimate"})
            continue
        if estimate <= 0:
            declined.append({"symbol": symbol, "reason": f"Estimated change {estimate:+.2f}% is not positive"})
            continue
        positive_count += 1
        if lower <= -40:
            declined.append({"symbol": symbol, "reason": "Historical analogue downside exceeded the -40% gate"})
            continue
        if symbol not in histories:
            declined.append({"symbol": symbol, "reason": "Verified matched daily history is unavailable"})
            continue
        risk_score = estimate - 0.10 * max(0.0, -lower) - 0.05 * max(0.0, upper - lower)
        if risk_score <= 0:
            declined.append({"symbol": symbol, "reason": "Positive estimate, but the downside/uncertainty penalty outweighs it"})
            continue
        reviewed.append(item)
        scores[symbol] = risk_score
    return reviewed, scores, declined, positive_count


def build_diversified_research_plan(
    budget: Decimal, *, style: Literal["cautious", "balanced", "growth"],
    horizon: Literal["short", "medium", "long"],
    max_loss_usd: Decimal | None,
    allow_exploratory: bool,
    ranked: Sequence[Mapping[str, Any]],
    histories: Mapping[str, Sequence[PricePoint]],
    benchmark: Mapping[str, Any] | None,
    allocation_mode: Literal["combined", "core_only", "stocks_only"] = "combined",
) -> dict[str, Any]:
    total = validate_budget(budget)
    cap = validate_max_loss(max_loss_usd, total)
    if horizon not in CORE_PCT or style not in CORE_PCT[horizon]:
        raise ValueError("Unsupported investment style or holding period.")
    if allocation_mode not in ("combined", "core_only", "stocks_only"):
        raise ValueError("Unsupported portfolio comparison approach.")
    cents = int(total * 100)
    available_risky = int(cap * 100) if cap is not None else cents
    core_pct = CORE_PCT[horizon][style]
    stock_pct = STOCK_PCT[horizon][style]
    core = 0 if allocation_mode == "stocks_only" else min(
        cents * core_pct // 100, available_risky,
    )
    period = HORIZON_TO_FORECAST[horizon]
    declined: list[dict[str, str]] = []

    if core and benchmark is not None:
        forecast = benchmark.get("horizons", {}).get(period, {})
        estimate = forecast.get("estimated_change_pct") if isinstance(forecast, Mapping) else None
        if (
            not isinstance(estimate, (int, float))
            or isinstance(estimate, bool)
            or not math.isfinite(estimate)
        ):
            core = 0
            declined.append({"symbol": "SPY", "reason": "No usable positive SPY estimate for this period"})
        elif estimate <= 0:
            core = 0
            declined.append({"symbol": "SPY", "reason": f"SPY estimate {estimate:+.2f}% is not positive"})

    if allocation_mode == "core_only":
        stock_budget = 0
    elif allocation_mode == "stocks_only":
        # Same style/horizon risky-asset sleeve as the blended scenario,
        # but never bypass 10%-per-stock and four-stock concentration caps.
        stock_budget = min(cents * (core_pct + stock_pct) // 100, available_risky)
    else:
        stock_budget = min(cents * stock_pct // 100, available_risky - core)
    reviewed: list[Mapping[str, Any]] = []
    scores: dict[str, float] = {}
    positive_count = 0
    if allow_exploratory and stock_budget > 0:
        reviewed, scores, filtered_out, positive_count = screen_ranked_stock_candidates(
            ranked, histories,
        )
        declined.extend(filtered_out)

    picked, evaluated = _basket_choice(
        reviewed, scores, histories, budget_cents=cents, stock_cents=stock_budget,
    ) if reviewed else ([], 0)
    chosen = {str(row["symbol"]) for row, _ in picked}
    for item in reviewed:
        if str(item["symbol"]) not in chosen:
            declined.append({
                "symbol": str(item["symbol"]),
                "reason": "Not selected by the combination, concentration and correlation checks",
            })

    allocations: list[dict[str, Any]] = []
    gain = Decimal(0)
    if core:
        allocations.append({
            "symbol": "SPY", "category": "diversified_core", "amount_usd": _usd(core),
            "percent_of_budget": round(100 * core / cents, 2),
            "why": "Diversified U.S. large-company fund (illustrative example)",
        })
        if benchmark is not None:
            sp = benchmark.get("horizons", {}).get(period, {})
            if isinstance(sp, Mapping):
                gain += Decimal(core) * Decimal(str(sp["estimated_change_pct"])) / 10_000
    stock_used = 0
    for item, amount in picked:
        if amount <= 0:
            continue
        stock_used += amount
        gain += Decimal(amount) * Decimal(str(item["estimated_change_pct"])) / 10_000
        allocations.append({
            "symbol": item["symbol"], "category": "experimental_stock",
            "amount_usd": _usd(amount),
            "percent_of_budget": round(100 * amount / cents, 2),
            "why": "Risk-scored exploratory combination; no guaranteed return",
            "estimated_change_pct": item["estimated_change_pct"],
            "analogue_low_pct": item["historical_analogue_low_pct"],
            "analogue_high_pct": item["historical_analogue_high_pct"],
            "backtest": item["backtest"],
        })
    cash = cents - core - stock_used
    allocations.append({
        "symbol": None, "category": "cash", "amount_usd": _usd(cash),
        "percent_of_budget": round(100 * cash / cents, 2),
        "why": "Unallocated funds, including positions without enough supporting evidence",
    })
    assert sum(int(Decimal(row["amount_usd"]) * 100) for row in allocations) == cents
    return {
        "version": "growth-research-scenario-v2", "budget_usd": _usd(cents),
        "invested_usd": _usd(core + stock_used), "cash_usd": _usd(cash),
        "style": style, "horizon": horizon, "forecast_period": period,
        "allocation_mode": allocation_mode,
        "forecast_horizon_sessions": {"short": 20, "medium": 60, "long": 120}[horizon],
        "max_loss_usd": str(cap) if cap is not None else None,
        "exploratory": allow_exploratory, "allocation": allocations, "declined": declined,
        "combination_analysis": {
            "method": "bounded_risk_adjusted_historical_heuristic_not_probability",
            "forecasted_stocks_reviewed": len(ranked) if allow_exploratory else 0,
            "positive_estimate_stocks": positive_count,
            "risk_eligible_stocks": len(reviewed),
            "combinations_considered": evaluated,
            "stock_positions_selected": len(picked),
            "illustrative_model_gain_usd": str(gain.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        },
        "current_model_status": "historical_backtest_only_not_prospectively_validated",
        "benchmark_estimated_change_pct": (
            benchmark.get("horizons", {}).get(period, {}).get("estimated_change_pct")
            if benchmark is not None else None
        ),
        "warning": (
            "The basket uses risk-adjusted historical analogue estimates, not a validated "
            "probability of gain or a known maximum-profit combination. "
            "Non-positive estimates receive no allocation, including SPY. Positive estimates "
            "can still lose money. Concentration and correlation screens limit allocations "
            "but do NOT bound losses. Any projected gain is experimental for the short "
            "forecast period, not your full holding period. All dollars are illustrative; "
            "no trade is placed."
        ),
    }
