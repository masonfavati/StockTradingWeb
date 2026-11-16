"""Exhaustive *screened-subset* search for the largest modeled dollar change.

For each feasible stock subset (up to four, drawn from all <=20 screened
forecasts), the optimum of the linear six-month dollar objective under the
existing principal, sleeve and single-stock caps is found exactly in cents:
reserve the 1% per-selected-stock minimum, then fill highest-estimate assets
first. This is NOT an exhaustive U.S. market forecast or a prediction of profit.
"""

import math
from collections.abc import Mapping, Sequence
from decimal import ROUND_HALF_UP, Decimal
from itertools import combinations
from typing import Any, Literal

from app.analysis.budget_planner import validate_budget, validate_max_loss
from app.analysis.growth_allocation import (
    CORE_PCT,
    HORIZON_TO_FORECAST,
    MAX_BASKET_STOCKS,
    MAX_STOCK_PCT,
    STOCK_PCT,
    screen_ranked_stock_candidates,
)
from app.analysis.historical_growth import PricePoint, daily_correlation


def _money(cents: int) -> str:
    return f"{Decimal(cents) / 100:.2f}"


def _fill_optimal_cents(
    subset: Sequence[Mapping[str, Any]], *,
    include_spy: bool, total_cents: int, risky_cap_cents: int,
    stock_sleeve_cents: int, core_cap_cents: int,
    spy_estimate: Decimal | None,
) -> tuple[dict[str, int], Decimal] | None:
    """Solve a fixed subset's linear return objective exactly to one cent.

    All selected stocks receive >=1% of budget; all further dollars go to
    the highest percentage-estimate asset that still has available capacity.
    A positive-return SPY may compete with stocks for the same risky budget.
    """
    min_stock = max(1, total_cents // 100)
    per_stock_cap = total_cents * MAX_STOCK_PCT // 100
    reserved = len(subset) * min_stock
    if (
        (not subset and not include_spy)
        or per_stock_cap < min_stock
        or stock_sleeve_cents < reserved
        or risky_cap_cents < reserved
        or (include_spy and (core_cap_cents <= 0 or spy_estimate is None))
    ):
        return None
    allocations = {str(item["symbol"]): min_stock for item in subset}
    free_stock = stock_sleeve_cents - reserved
    free_risky = risky_cap_cents - reserved
    options: list[tuple[str, Decimal, int, bool]] = [
        (
            str(item["symbol"]),
            Decimal(str(item["estimated_change_pct"])),
            per_stock_cap - min_stock,
            True,
        )
        for item in subset
    ]
    if include_spy and spy_estimate is not None:
        options.append(("SPY", spy_estimate, core_cap_cents, False))
    for symbol, _estimate, capacity, is_stock in sorted(
        options, key=lambda row: (-row[1], row[0]),
    ):
        extra = min(free_risky, capacity, free_stock if is_stock else free_risky)
        if extra <= 0:
            continue
        allocations[symbol] = allocations.get(symbol, 0) + extra
        free_risky -= extra
        if is_stock:
            free_stock -= extra
    estimates = {
        str(item["symbol"]): Decimal(str(item["estimated_change_pct"]))
        for item in subset
    }
    if include_spy and spy_estimate is not None:
        estimates["SPY"] = spy_estimate
    # amount in cents × percentage / 10,000 => USD, no float rounding.
    gain_usd = sum(
        (Decimal(cents) * estimates[symbol] / Decimal(10_000)
         for symbol, cents in allocations.items()),
        Decimal(0),
    )
    return allocations, gain_usd


def build_max_model_growth_plan(
    budget: Decimal, *, style: Literal["cautious", "balanced", "growth"],
    horizon: Literal["short", "medium", "long"],
    max_loss_usd: Decimal | None,
    allow_exploratory: bool,
    ranked: Sequence[Mapping[str, Any]],
    histories: Mapping[str, Sequence[PricePoint]],
    benchmark: Mapping[str, Any] | None,
) -> dict[str, Any]:
    """Find max modeled dollars across every eligible <=4-stock subset.

    Two structures are enumerated for EACH subset: stocks+cash and
    SPY+stocks+cash (if SPY itself qualifies). The mathematically optimal
    cent-exact split for each subset is evaluated, not guessed from scores.
    """
    if len(ranked) > 20:
        raise ValueError("The maximum-gain comparison supports up to 20 screened forecasts.")
    total = validate_budget(budget)
    cap = validate_max_loss(max_loss_usd, total)
    if horizon not in CORE_PCT or style not in CORE_PCT[horizon]:
        raise ValueError("Unsupported investment style or holding period.")
    cents = int(total * 100)
    risky_cap = int(cap * 100) if cap is not None else cents
    core_cap = cents * CORE_PCT[horizon][style] // 100
    mixed_stock_cap = cents * STOCK_PCT[horizon][style] // 100
    stock_only_cap = cents * (CORE_PCT[horizon][style] + STOCK_PCT[horizon][style]) // 100
    period = HORIZON_TO_FORECAST[horizon]

    spy_estimate: Decimal | None = None
    if allow_exploratory and core_cap > 0 and benchmark is not None and "SPY" in histories:
        info = benchmark.get("horizons", {})
        forecast = info.get(period, {}) if isinstance(info, Mapping) else {}
        raw_estimate = forecast.get("estimated_change_pct") if isinstance(forecast, Mapping) else None
        if (isinstance(raw_estimate, (int, float)) and not isinstance(raw_estimate, bool)
                and math.isfinite(raw_estimate) and raw_estimate > 0):
            spy_estimate = Decimal(str(raw_estimate))

    reviewed: list[Mapping[str, Any]] = []
    declined: list[dict[str, str]] = []
    positive_count = 0
    if allow_exploratory and stock_only_cap > 0 and risky_cap > 0:
        reviewed, _scores, declined, positive_count = screen_ranked_stock_candidates(
            ranked, histories,
        )
    reviewed = sorted(reviewed, key=lambda row: str(row["symbol"]))
    pairwise: dict[tuple[str, str], float | None] = {}
    for first, second in combinations(reviewed, 2):
        a, b = str(first["symbol"]), str(second["symbol"])
        pairwise[(a, b)] = daily_correlation(histories[a], histories[b])

    best_gain = Decimal(0)
    best_positions: dict[str, int] = {}
    best_structure = "cash_only"
    examined = 0
    feasible = 0
    correlation_rejected = 0

    if spy_estimate is not None:
        examined += 1  # SPY-only alternative (empty stock subset).
        result = _fill_optimal_cents(
            (), include_spy=True, total_cents=cents, risky_cap_cents=risky_cap,
            stock_sleeve_cents=0, core_cap_cents=core_cap,
            spy_estimate=spy_estimate,
        )
        if result is not None:
            feasible += 1
            if result[1] > best_gain:
                best_positions, best_gain = result
                best_structure = "spy_only"

    for size in range(1, min(MAX_BASKET_STOCKS, len(reviewed)) + 1):
        for subset in combinations(reviewed, size):
            symbols = [str(item["symbol"]) for item in subset]
            valid_correlation = True
            for i, j in combinations(range(size), 2):
                corr = pairwise[(symbols[i], symbols[j])]
                if corr is None or corr >= 0.80:
                    valid_correlation = False
                    break
            for with_spy in (False, True) if spy_estimate is not None else (False,):
                examined += 1
                if not valid_correlation:
                    correlation_rejected += 1
                    continue
                result = _fill_optimal_cents(
                    subset, include_spy=with_spy,
                    total_cents=cents, risky_cap_cents=risky_cap,
                    stock_sleeve_cents=mixed_stock_cap if with_spy else stock_only_cap,
                    core_cap_cents=core_cap if with_spy else 0,
                    spy_estimate=spy_estimate,
                )
                if result is None:
                    continue
                feasible += 1
                positions, gain = result
                if gain > best_gain:
                    best_positions, best_gain = positions, gain
                    best_structure = "spy_and_stocks" if with_spy else "stocks_and_cash"

    allocations: list[dict[str, Any]] = []
    if best_positions.get("SPY", 0) > 0:
        amount = best_positions["SPY"]
        allocations.append({
            "symbol": "SPY", "category": "diversified_core", "amount_usd": _money(amount),
            "percent_of_budget": round(100 * amount / cents, 2),
            "why": "SPY qualified for the largest experimental model-dollar change, within the risk cap",
        })
    picked_symbols = set(best_positions) - {"SPY"}
    for item in reviewed:
        symbol = str(item["symbol"])
        amount = best_positions.get(symbol, 0)
        if amount > 0:
            allocations.append({
                "symbol": symbol, "category": "experimental_stock", "amount_usd": _money(amount),
                "percent_of_budget": round(100 * amount / cents, 2),
                "why": "Highest experimental modeled dollar change under existing safety gates",
                "estimated_change_pct": item["estimated_change_pct"],
                "analogue_low_pct": item["historical_analogue_low_pct"],
                "analogue_high_pct": item["historical_analogue_high_pct"],
                "backtest": item["backtest"],
            })
        else:
            declined.append({
                "symbol": symbol,
                "reason": "Not selected in the maximum modeled-dollar comparison",
            })
    invested = sum(best_positions.values())
    allocations.append({
        "symbol": None, "category": "cash", "amount_usd": _money(cents - invested),
        "percent_of_budget": round(100 * (cents - invested) / cents, 2),
        "why": "Remaining funds after the model-gain search, budget caps and concentration safeguards",
    })
    assert sum(int(Decimal(row["amount_usd"]) * 100) for row in allocations) == cents
    return {
        "budget_usd": _money(cents),
        "invested_usd": _money(invested),
        "cash_usd": _money(cents - invested),
        "allocation": allocations,
        "declined": declined,
        "forecast_period": period,
        "forecast_horizon_sessions": {"short": 20, "medium": 60, "long": 120}[horizon],
        "combination_analysis": {
            "method": "exhaustive_screened_subsets_exact_linear_model_dollar_optimum_not_probability",
            "forecasted_stocks_reviewed": len(ranked) if allow_exploratory else 0,
            "positive_estimate_stocks": positive_count,
            "risk_eligible_stocks": len(reviewed),
            "combinations_considered": examined,
            "combinations_feasible": feasible,
            "correlation_rejected": correlation_rejected,
            "stock_positions_selected": len(picked_symbols),
            "winning_structure": best_structure,
            "illustrative_model_gain_usd": str(best_gain.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
        },
    }
