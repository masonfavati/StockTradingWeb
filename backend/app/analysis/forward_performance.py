"""Read-only, grouped descriptive statistics for verified prospective outcomes.

This is NOT a tradable equity curve, an independent-sample inference, or a
probability that a stock or strategy will be profitable. All registered
checkpoints remain in scope even when outcomes are missing.
"""

from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.analysis.forward_outcomes import (
    FIXED_COST_BPS,
    OutcomeStatus,
    _read_existing,
    outcome_status,
)

REPORT_SCHEMA = "forward-performance-summary-v1"
_STEP = Decimal("0.0001")
_ZERO = Decimal(0)


class PerformanceReportError(ValueError):
    """A source audit cannot support the claimed descriptive measurements."""


@dataclass(frozen=True)
class VerifiedObservation:
    signal: date
    entry: date
    exit: date
    selected_pct: Decimal
    benchmark_pct: Decimal
    excess_pp: Decimal
    profitable_stocks: int
    total_stocks: int
    checkpoint_sha256: str
    outcome_sha256: str


def _finite_decimal(raw: Any, *, label: str) -> Decimal:
    if not isinstance(raw, str):
        raise PerformanceReportError(f"{label} must be a decimal string")
    try:
        value = Decimal(raw)
    except InvalidOperation as exc:
        raise PerformanceReportError(f"{label} must be numeric") from exc
    if not value.is_finite():
        raise PerformanceReportError(f"{label} must be finite")
    return value


def _number(value: Decimal) -> str:
    return str(value.quantize(_STEP))


def _mean(values: list[Decimal]) -> Decimal:
    return sum(values, _ZERO) / Decimal(len(values))


def _verify_price_math(row: dict[str, Any], cost: Decimal) -> Decimal:
    """Independently recalculate a displayed net % from both recorded opens."""
    symbol = row.get("symbol")
    opening = _finite_decimal(row.get("entry_open_split_adjusted"), label=f"{symbol} entry open")
    exiting = _finite_decimal(row.get("exit_open_split_adjusted"), label=f"{symbol} exit open")
    gross = _finite_decimal(row.get("gross_return_pct"), label=f"{symbol} gross return")
    reported = _finite_decimal(row.get("net_return_pct"), label=f"{symbol} net return")
    if opening <= 0 or exiting <= 0:
        raise PerformanceReportError(f"{symbol} outcome uses a nonpositive opening price")
    calculated_gross = (exiting / opening - Decimal(1)) * Decimal(100)
    calculated_net = (
        exiting * (Decimal(1) - cost) / (opening * (Decimal(1) + cost))
        - Decimal(1)
    ) * Decimal(100)
    if gross != calculated_gross.quantize(_STEP) or reported != calculated_net.quantize(_STEP):
        raise PerformanceReportError(f"{symbol} recorded return disagrees with frozen opening prices")
    return reported


def _verified_observation(item: OutcomeStatus) -> VerifiedObservation:
    if item.state != "COMPLETE":
        raise PerformanceReportError("Non-complete outcomes cannot contribute to return statistics")
    entry = item.row.entry
    body = _read_existing(item.audit_path, entry)
    if body["status"] != "complete":
        raise PerformanceReportError("Incomplete outcome cannot claim a complete observation")
    try:
        opening = date.fromisoformat(body["entry_session"])
        closing = date.fromisoformat(body["exit_session"])
    except (ValueError, TypeError, KeyError) as exc:
        raise PerformanceReportError("Outcome has invalid entry/exit dates") from exc
    if not entry.checkpoint.signal_session < opening < closing:
        raise PerformanceReportError("Outcome entry/exit dates are not strictly forward-looking")
    chosen = body["selected_outcomes"]
    benchmark = body["benchmark_outcome"]
    comparison = body["complete_portfolio_comparison"]
    cost = FIXED_COST_BPS / Decimal(10_000)
    stock_returns = [_verify_price_math(row, cost) for row in chosen]
    if not stock_returns:
        raise PerformanceReportError("Empty shortlist cannot contribute performance")
    if benchmark.get("status") != "complete":
        raise PerformanceReportError("A complete comparison requires a complete SPY outcome")
    benchmark_from_prices = _verify_price_math(benchmark, cost)
    selected = _finite_decimal(
        comparison.get("selected_equal_weight_net_return_pct"), label="Selected portfolio return"
    )
    spy = _finite_decimal(comparison.get("benchmark_net_return_pct"), label="SPY return")
    excess = _finite_decimal(
        comparison.get("excess_vs_benchmark_percentage_points"), label="Paired excess return"
    )
    average = _mean(stock_returns)
    if (
        selected != average.quantize(_STEP)
        or spy != benchmark_from_prices
        or excess != (average - spy).quantize(_STEP)
        or type(comparison.get("selected_winners_after_costs")) is not int
        or comparison["selected_winners_after_costs"] != sum(value > 0 for value in stock_returns)
        or type(comparison.get("selected_beats_benchmark")) is not bool
        or comparison["selected_beats_benchmark"] != (average > spy)
    ):
        raise PerformanceReportError("Portfolio comparison disagrees with per-stock outcomes")
    return VerifiedObservation(
        signal=entry.checkpoint.signal_session,
        entry=opening,
        exit=closing,
        selected_pct=selected,
        benchmark_pct=spy,
        excess_pp=excess,
        profitable_stocks=sum(value > 0 for value in stock_returns),
        total_stocks=len(stock_returns),
        checkpoint_sha256=entry.expected_sha256,
        outcome_sha256=body["content_sha256"],
    )


def _overlap_diagnostics(items: list[VerifiedObservation]) -> dict[str, int]:
    """Open-to-open exposure overlaps iff entry_A < exit_B and vice versa."""
    chronological = sorted(items, key=lambda row: (row.entry, row.exit, row.signal))
    overlapping: set[int] = set()
    pairs = 0
    for i, first in enumerate(chronological):
        for j in range(i + 1, len(chronological)):
            second = chronological[j]
            if second.entry >= first.exit:
                break
            pairs += 1
            overlapping.update((i, j))
    events = sorted(
        [event for item in chronological for event in ((item.entry, 1), (item.exit, -1))],
        key=lambda pair: (pair[0], pair[1]),
    )
    concurrent = 0
    maximum = 0
    for _day, change in events:
        concurrent += change
        maximum = max(maximum, concurrent)
    chosen = 0
    last_exit: date | None = None
    for item in sorted(chronological, key=lambda row: (row.exit, row.entry)):
        if last_exit is None or item.entry >= last_exit:
            chosen += 1
            last_exit = item.exit
    return {
        "overlapping_pairs": pairs,
        "observations_with_overlap": len(overlapping),
        "maximum_simultaneous_windows": maximum,
        "maximum_date_disjoint_windows": chosen,
    }


def _metrics(items: list[VerifiedObservation]) -> dict[str, Any] | None:
    if not items:
        return None
    selected = [item.selected_pct for item in items]
    spy = [item.benchmark_pct for item in items]
    excess = [item.excess_pp for item in items]
    avg_excess = _mean(excess)
    # This is descriptive dispersion of overlapping holding-period results,
    # NOT a standard error, Sharpe ratio, uncertainty bound, or annualized risk.
    variance = _mean([(value - avg_excess) ** 2 for value in excess])
    ordered_excess = sorted(excess)
    middle = len(ordered_excess) // 2
    midpoint = (
        ordered_excess[middle] if len(ordered_excess) % 2
        else (ordered_excess[middle - 1] + ordered_excess[middle]) / Decimal(2)
    )
    return {
        "mean_selected_net_pct": _number(_mean(selected)),
        "mean_spy_net_pct": _number(_mean(spy)),
        "mean_paired_excess_pp": _number(avg_excess),
        "median_paired_excess_pp": _number(midpoint),
        "best_paired_excess_pp": _number(max(excess)),
        "worst_paired_excess_pp": _number(min(excess)),
        "descriptive_excess_dispersion_pp": _number(variance.sqrt()),
        "positive_selected_windows": sum(value > 0 for value in selected),
        "windows_beating_spy": sum(value > 0 for value in excess),
        "complete_windows": len(items),
    }


def build_performance_report(root: Path, *, now: datetime | None = None) -> dict[str, Any]:
    """Inventory ALL registered forward checkpoints; never fetch price outcomes.

    The existing journal checks every checkpoint, pin and outcome hash. Any
    inconsistent audit blocks the entire report instead of being dropped.
    """
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise PerformanceReportError("Report time must include a time zone")
    statuses = outcome_status(root, now=current)
    groups: dict[tuple[str, int], list[OutcomeStatus]] = defaultdict(list)
    for item in statuses:
        cp = item.row.entry.checkpoint
        groups[(cp.research_rule, cp.horizon)].append(item)
    summaries: list[dict[str, Any]] = []
    states = ("PENDING", "READY", "COMPLETE", "INCOMPLETE", "NO_SELECTION")
    overall = {state: sum(item.state == state for item in statuses) for state in states}
    for (rule, horizon), members in sorted(groups.items()):
        counts = {state: sum(item.state == state for item in members) for state in states}
        completed = [_verified_observation(item) for item in members if item.state == "COMPLETE"]
        completed.sort(key=lambda item: item.signal)
        summaries.append({
            "research_rule": rule,
            "holding_sessions": horizon,
            "registered_checkpoints": len(members),
            "status_counts": counts,
            "metrics": _metrics(completed),
            "overlap": _overlap_diagnostics(completed),
            "completed_observations": [
                {
                    "signal_session": row.signal.isoformat(),
                    "entry_session": row.entry.isoformat(),
                    "exit_session": row.exit.isoformat(),
                    "selected_equal_weight_net_pct": _number(row.selected_pct),
                    "spy_net_pct": _number(row.benchmark_pct),
                    "paired_excess_pp": _number(row.excess_pp),
                    "profitable_stocks_after_costs": row.profitable_stocks,
                    "selected_stocks": row.total_stocks,
                    "checkpoint_sha256": row.checkpoint_sha256,
                    "outcome_sha256": row.outcome_sha256,
                }
                for row in completed
            ],
        })
    return {
        "schema_version": REPORT_SCHEMA,
        "generated_at_utc": current.astimezone(UTC).isoformat(),
        "registered_checkpoints": len(statuses),
        "status_counts": overall,
        "groups": summaries,
        "warnings": [
            "Only COMPLETE outcomes enter returns; READY, PENDING, INCOMPLETE, and NO_SELECTION remain counted.",
            "Groups with different frozen research rules or holding horizons are NEVER pooled.",
            "Overlapping horizons are correlated; averages are NOT a tradable equity curve, CAGR, or independent trials.",
            "Completion bias can distort the complete-only averages. No missing outcome is substituted or assigned zero.",
            "Raw arithmetic is checked against recorded split-adjusted openings; no provider price refresh occurs.",
            "Dividends, delisting proceeds, mergers, spread variation, taxes and market impact are not fully modeled.",
            "Local hashes and timestamps are not independently certified; no predictive skill or profit is established.",
        ],
    }
