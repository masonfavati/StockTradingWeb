"""Transparent comparison of three hypothetical, same-budget portfolio approaches.

A fixed-weight, retrospective price exercise is NOT a probability model, a
validated backtest of the security-selection strategy, or a maximum-loss bound.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import date
from decimal import Decimal
from typing import Any

from app.analysis.historical_growth import PricePoint

APPROACHES = (
    ("combined", "SPY + eligible individual stocks"),
    ("core_only", "SPY fund + cash"),
    ("max_model_change", "Highest experimental model dollar change"),
)


def _past_window_range(
    plans: Mapping[str, Mapping[str, Any]],
    histories: Mapping[str, Sequence[PricePoint]],
    horizon_sessions: int,
) -> dict[str, dict[str, int | float] | None]:
    """Compare *same-date*, non-overlapping windows at static initial weights.

    Current surviving securities are projected into past windows, so the
    results have survivorship/selection bias. These results are descriptive
    scenario checks and MUST NEVER be represented as live-model validation.
    """
    symbols = {
        str(row["symbol"])
        for plan in plans.values()
        for row in plan["allocation"]
        if row["category"] != "cash" and row["symbol"] is not None
        and Decimal(str(row["amount_usd"])) > 0
    }
    none_available: dict[str, dict[str, int | float] | None] = {
        key: None for key in plans
    }
    if not symbols or horizon_sessions <= 0:
        return none_available
    price_maps: dict[str, dict[date, float]] = {}
    for symbol in symbols:
        prices = histories.get(symbol)
        if not prices:
            return none_available
        by_day = {row.day: row.close for row in prices}
        if not by_day or any(not math.isfinite(v) or v <= 0 for v in by_day.values()):
            return none_available
        price_maps[symbol] = by_day
    matching = sorted(set.intersection(*(set(row) for row in price_maps.values())))
    if len(matching) <= horizon_sessions:
        return none_available

    # Work backwards from the last shared session using disjoint windows.
    # Keep the same dates for all three comparisons, including the fund-only
    # scenario; otherwise two different market periods could be compared.
    window_indices: list[tuple[int, int]] = []
    last = len(matching) - 1
    while last >= horizon_sessions:
        window_indices.append((last - horizon_sessions, last))
        last -= horizon_sessions

    results: dict[str, dict[str, int | float] | None] = {}
    for key, plan in plans.items():
        invested = [
            row for row in plan["allocation"]
            if row["category"] != "cash" and row["symbol"] is not None
            and Decimal(str(row["amount_usd"])) > 0
        ]
        if not invested:
            results[key] = None  # Entirely cash; no risky historic comparison.
            continue
        budget = float(Decimal(str(plan["budget_usd"])))
        changes = []
        for start, end in window_indices:
            first, final = matching[start], matching[end]
            change = 0.0
            for row in invested:
                symbol = str(row["symbol"])
                weight = float(Decimal(str(row["amount_usd"]))) / budget
                change += 100 * weight * (
                    price_maps[symbol][final] / price_maps[symbol][first] - 1
                )
            changes.append(change)
        results[key] = {
            "windows_compared": len(changes),
            "worst_observed_change_pct": round(min(changes), 2),
            "best_observed_change_pct": round(max(changes), 2),
        }
    return results


def compare_scenarios(
    plans: Mapping[str, Mapping[str, Any]],
    histories: Mapping[str, Sequence[PricePoint]],
    *, stock_allocation_authorized: bool,
) -> dict[str, Any]:
    """Same inputs and budget for three possible illustrations, no extra API IO."""
    expected = {key for key, _ in APPROACHES}
    if set(plans) != expected:
        raise ValueError("All three portfolio approaches are required.")
    horizon_sessions = int(plans["combined"]["forecast_horizon_sessions"])
    past = _past_window_range(plans, histories, horizon_sessions)
    rows: list[dict[str, Any]] = []
    for key, label in APPROACHES:
        plan = plans[key]
        allocation = plan["allocation"]
        stock_count = sum(
            row["category"] == "experimental_stock"
            and Decimal(str(row["amount_usd"])) > 0
            for row in allocation
        )
        available = key != "max_model_change" or stock_allocation_authorized
        if key == "max_model_change" and not available:
            explanation = (
                "Maximum-change comparison requires opting into experimental stocks "
                "and a recent quality-verified full-market shortlist. Unscreened "
                "stock positions are never illustrated."
            )
        elif Decimal(str(plan["invested_usd"])) == 0:
            explanation = (
                "No positions qualified under the selected estimates and "
                "risk caps. The entire example remains cash."
            )
        elif key == "max_model_change":
            analysis = plan["combination_analysis"]
            mode = analysis["winning_structure"]
            chosen = {
                "spy_and_stocks": "SPY + eligible stocks + cash",
                "stocks_and_cash": "Eligible stocks + cash (no SPY)",
                "spy_only": "SPY + cash (no eligible stock improved the estimate)",
                "cash_only": "Cash only (no positive eligible investment estimate)",
            }[mode]
            explanation = (
                f"Selected: {chosen}. Examined {analysis['combinations_considered']:,} "
                f"eligible subset/structure combinations, with "
                f"{analysis['combinations_feasible']:,} meeting dollar and correlation "
                "constraints. Each feasible combination's dollar split was optimized "
                "to maximize the experimental model-dollar change. This is NOT a "
                "validated most-likely-to-profit strategy."
            )
        elif key == "core_only":
            explanation = "One diversified S&P 500 fund example; no individual-stock positions."
        else:
            explanation = "Combined diversified-fund and quality-screened stock example."
        rows.append({
            "id": key,
            "label": label,
            "available": available,
            "allocation": allocation,
            "invested_usd": plan["invested_usd"],
            "cash_usd": plan["cash_usd"],
            "stock_positions": stock_count,
            "illustrative_model_gain_usd": (
                plan["combination_analysis"]["illustrative_model_gain_usd"]
                if available else None
            ),
            "past_window_range": past[key] if available else None,
            "explanation": explanation,
            "winning_structure": (
                plan["combination_analysis"]["winning_structure"]
                if key == "max_model_change" and available else None
            ),
            "combinations_considered": (
                plan["combination_analysis"]["combinations_considered"]
                if key == "max_model_change" and available else None
            ),
        })
    return {
        "forecast_period": plans["combined"]["forecast_period"],
        "forecast_horizon_sessions": horizon_sessions,
        "approaches": rows,
        "method_warning": (
            "The maximum-change approach searches ALL eligible subsets of up to four "
            "of at most 20 previously screened stocks, with/without SPY, and solves "
            "the linear model-gain allocation in cents within existing risk/sleeve "
            "and 10%-per-stock caps. It does NOT forecast the entire market or "
            "guarantee the best real-world portfolio. "
            "The model-dollar change is an unvalidated short-horizon estimate, "
            "not a predicted profit or probability. Historical best/worst "
            "figures are observed changes in disjoint, same-date past windows "
            "with today's surviving securities and fixed beginning-of-window "
            "dollar weights; they are selection-biased, not tested strategy "
            "results or limits on future losses. Comparisons can invest "
            "different amounts because of the same concentration and "
            "budget-risk caps. No orders are placed."
        ),
    }
