"""Audit frozen prospective scanner picks at a predeclared open-to-open horizon.

NEVER use outcome-day prices to change the original shortlist. This is one
prospective observation, not a validated profitable trading strategy.
"""

import hashlib
import json
import re
from collections.abc import Mapping, Sequence
from collections.abc import Set as AbstractSet
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dt_time
from decimal import Decimal
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.analysis.forward_record import SCHEMA_VERSION
from app.market_data.history_client import DailyBar

NY = ZoneInfo("America/New_York")
OUTCOME_SCHEMA = "forward-outcome-audit-v1"
BENCHMARK = "SPY"
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")
_CHECKSUM = re.compile(r"[0-9a-f]{64}\Z")
_PCT_STEP = Decimal("0.0001")


class ForwardEvaluationError(ValueError):
    """Fail closed on altered checkpoints and inconsistent evaluation inputs."""


@dataclass(frozen=True)
class FrozenCheckpoint:
    content_sha256: str
    recorded_at_utc: datetime
    signal_session: date
    horizon: int
    shortlist: tuple[str, ...]
    research_rule: str


@dataclass(frozen=True)
class EvaluationWindow:
    observed_future_sessions: int
    required_future_sessions: int
    entry_session: date | None
    exit_session: date | None

    @property
    def is_mature(self) -> bool:
        return self.exit_session is not None


def _unique_json_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise ForwardEvaluationError(f"Duplicate JSON key in checkpoint: {key}")
        result[key] = value
    return result


def _reject_nonfinite_constant(value: str) -> None:
    raise ForwardEvaluationError(f"Nonfinite JSON value in checkpoint: {value}")


def load_checkpoint(path: Path, *, expected_checksum: str) -> FrozenCheckpoint:
    """Verify the original canonical hash AND a separately retained checksum."""
    if _CHECKSUM.fullmatch(expected_checksum) is None:
        raise ForwardEvaluationError("Expected checksum must be a lowercase SHA-256 hex digest")
    if path.stat().st_size > 1_000_000:
        raise ForwardEvaluationError("Checkpoint is unexpectedly large")
    try:
        body: Any = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_json_pairs,
            parse_constant=_reject_nonfinite_constant,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ForwardEvaluationError("Checkpoint is not valid UTF-8 JSON") from exc
    if not isinstance(body, dict):
        raise ForwardEvaluationError("Checkpoint must be a JSON object")
    claimed = body.get("content_sha256")
    content = {key: value for key, value in body.items() if key != "content_sha256"}
    canonical = json.dumps(content, sort_keys=True, separators=(",", ":"), allow_nan=False)
    actual = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    if claimed != expected_checksum or actual != expected_checksum:
        raise ForwardEvaluationError("Checkpoint content SHA-256 mismatch; record is not trusted")
    if (
        body.get("schema_version") != SCHEMA_VERSION
        or body.get("data_provider") != "alpaca"
        or body.get("feed") != "sip"
        or body.get("adjustment") != "all"
        or body.get("hypothetical_next_session_open_entry") is not True
    ):
        raise ForwardEvaluationError("Unsupported prospective checkpoint schema or research protocol")
    horizon = body.get("hypothetical_holding_sessions")
    if type(horizon) is not int or not 1 <= horizon <= 252:
        raise ForwardEvaluationError("Invalid frozen holding horizon")
    symbols = body.get("shortlist")
    if not isinstance(symbols, list) or len(symbols) > 20:
        raise ForwardEvaluationError("Invalid frozen shortlist")
    selected: list[str] = []
    try:
        signal = date.fromisoformat(body["last_completed_market_session"])
        recorded = datetime.fromisoformat(body["recorded_at_utc"])
    except (TypeError, ValueError, KeyError) as exc:
        raise ForwardEvaluationError("Invalid checkpoint date or timestamp") from exc
    if recorded.tzinfo is None or recorded.utcoffset() is None:
        raise ForwardEvaluationError("Checkpoint timestamp must be timezone-aware")
    if signal >= recorded.astimezone(NY).date():
        raise ForwardEvaluationError("Checkpoint was not recorded after its signal session")
    for item in symbols:
        if not isinstance(item, dict):
            raise ForwardEvaluationError("Invalid shortlist row")
        symbol = item.get("symbol")
        if (
            not isinstance(symbol, str)
            or _SYMBOL.fullmatch(symbol) is None
            or item.get("last_session") != signal.isoformat()
            or symbol in selected
        ):
            raise ForwardEvaluationError("Invalid, duplicate, or stale frozen selection")
        selected.append(symbol)
    rule = body.get("research_rule")
    if not isinstance(rule, str) or not rule:
        raise ForwardEvaluationError("Frozen research rule is missing")
    return FrozenCheckpoint(
        content_sha256=actual,
        recorded_at_utc=recorded.astimezone(UTC),
        signal_session=signal,
        horizon=horizon,
        shortlist=tuple(selected),
        research_rule=rule,
    )


def before_entry_open(recorded_at: datetime, entry_session: date) -> bool:
    """Conservative prospective timing rule shared by capture and evaluator.

    A checkpoint may be recorded on the entry date ONLY if the whole
    scan finishes strictly before 09:00 New York time, at least 30 minutes
    ahead of the US equities' regular 09:30 open. Earlier dates remain valid.
    The calendar verifies the session DATE; we intentionally enforce a
    stricter fixed pre-open cutoff rather than assuming a fill at 09:30.
    """
    if recorded_at.tzinfo is None or recorded_at.utcoffset() is None:
        raise ForwardEvaluationError("Recording timestamp must include a time zone")
    ny = recorded_at.astimezone(NY)
    return ny.date() < entry_session or (
        ny.date() == entry_session and ny.time() < dt_time(9)
    )


def evaluation_window(
    checkpoint: FrozenCheckpoint,
    *,
    sessions: AbstractSet[date],
    completed_through: date,
) -> EvaluationWindow:
    """Entry: next exchange open. Exit: horizon EXCHANGE opens after entry.

    A horizon of 20 needs 21 future exchange sessions: 1 entry + 20.
    """
    if checkpoint.signal_session not in sessions:
        raise ForwardEvaluationError("Frozen signal date is not a verified exchange session")
    if any(day > completed_through for day in sessions):
        raise ForwardEvaluationError("Calendar includes sessions after the completed-day cutoff")
    future = sorted(day for day in sessions if day > checkpoint.signal_session)
    entry = future[0] if future else None
    if entry is not None and not before_entry_open(checkpoint.recorded_at_utc, entry):
        raise ForwardEvaluationError(
            "Checkpoint was not recorded before the conservative 09:00 NY "
            "next-session entry deadline; entry cannot be reconstructed safely"
        )
    required = checkpoint.horizon + 1
    exit_session = future[checkpoint.horizon] if len(future) >= required else None
    return EvaluationWindow(
        observed_future_sessions=len(future),
        required_future_sessions=required,
        entry_session=entry,
        exit_session=exit_session,
    )


def validate_cost(cost_bps_per_side: Decimal) -> Decimal:
    if not cost_bps_per_side.is_finite() or not Decimal(0) <= cost_bps_per_side <= Decimal(500):
        raise ForwardEvaluationError("Per-side cost must be 0–500 basis points")
    return cost_bps_per_side / Decimal(10_000)


def _percent(ratio: Decimal) -> str:
    return str((ratio * Decimal(100)).quantize(_PCT_STEP))


def _instrument_outcome(
    symbol: str,
    *,
    by_date: Mapping[date, DailyBar],
    entry: date,
    exit_: date,
    cost: Decimal,
    invalid_symbols: AbstractSet[str],
    duplicate_symbols: AbstractSet[str],
) -> dict[str, Any]:
    row: dict[str, Any] = {"symbol": symbol, "status": "complete"}
    if symbol in invalid_symbols:
        row["status"] = "invalid_core_bar"
    elif symbol in duplicate_symbols:
        row["status"] = "duplicate_session_bar"
    elif entry not in by_date:
        row["status"] = "missing_entry_open"
    elif exit_ not in by_date:
        row["status"] = "missing_exit_open"
    else:
        opening = by_date[entry].open_price
        closing = by_date[exit_].open_price
        if (
            not opening.is_finite() or opening <= 0
            or not closing.is_finite() or closing <= 0
        ):
            row["status"] = "invalid_price"
        else:
            gross = closing / opening - Decimal(1)
            net = closing * (Decimal(1) - cost) / (opening * (Decimal(1) + cost)) - Decimal(1)
            row.update({
                "entry_open_split_adjusted": str(opening),
                "exit_open_split_adjusted": str(closing),
                "gross_return_pct": _percent(gross),
                "net_return_pct": _percent(net),
            })
    return row


def build_outcome_audit(
    checkpoint: FrozenCheckpoint,
    window: EvaluationWindow,
    *,
    bars: Sequence[DailyBar],
    invalid_symbols: AbstractSet[str],
    cost_bps_per_side: Decimal,
    evaluated_at: datetime,
) -> dict[str, Any]:
    """Produce a diagnostic; portfolio comparison only with 100% price coverage."""
    if not window.is_mature or window.entry_session is None or window.exit_session is None:
        raise ForwardEvaluationError("Outcomes cannot be calculated before the exit session")
    if evaluated_at.tzinfo is None or evaluated_at.utcoffset() is None:
        raise ForwardEvaluationError("Evaluation timestamp must have a time zone")
    cost = validate_cost(cost_bps_per_side)
    symbols = set(checkpoint.shortlist) | {BENCHMARK}
    prices: dict[str, dict[date, DailyBar]] = {symbol: {} for symbol in symbols}
    duplicates: set[str] = set()
    for bar in bars:
        if bar.symbol not in symbols:
            raise ForwardEvaluationError("Provider returned a symbol outside the frozen outcome request")
        if bar.session_date > window.exit_session:
            raise ForwardEvaluationError("Outcome data contains a session after the frozen exit date")
        if bar.session_date not in (window.entry_session, window.exit_session):
            continue
        if bar.session_date in prices[bar.symbol]:
            duplicates.add(bar.symbol)
        else:
            prices[bar.symbol][bar.session_date] = bar
    if not set(invalid_symbols) <= symbols:
        raise ForwardEvaluationError("Malformed-price reports contain an unexpected symbol")
    per_stock = [
        {"rank": rank, **_instrument_outcome(
            symbol, by_date=prices[symbol], entry=window.entry_session,
            exit_=window.exit_session, cost=cost, invalid_symbols=invalid_symbols,
            duplicate_symbols=duplicates,
        )}
        for rank, symbol in enumerate(checkpoint.shortlist, start=1)
    ]
    benchmark = _instrument_outcome(
        BENCHMARK, by_date=prices[BENCHMARK], entry=window.entry_session,
        exit_=window.exit_session, cost=cost, invalid_symbols=invalid_symbols,
        duplicate_symbols=duplicates,
    )
    complete_stocks = all(row["status"] == "complete" for row in per_stock)
    complete_benchmark = benchmark["status"] == "complete"
    status = (
        "no_selection" if not per_stock
        else "complete" if complete_stocks and complete_benchmark
        else "incomplete_outcomes"
    )
    comparison: dict[str, Any] | None = None
    if status == "complete":
        # Use unrounded percent return strings, which are precise to 0.0001%.
        # This rounding is insignificant compared with assumed execution costs.
        selected = [Decimal(row["net_return_pct"]) for row in per_stock]
        average = sum(selected, Decimal(0)) / Decimal(len(selected))
        baseline = Decimal(benchmark["net_return_pct"])
        comparison = {
            "selected_equal_weight_net_return_pct": str(average.quantize(_PCT_STEP)),
            "benchmark_net_return_pct": str(baseline),
            "excess_vs_benchmark_percentage_points": str((average - baseline).quantize(_PCT_STEP)),
            "selected_winners_after_costs": sum(value > 0 for value in selected),
            "selected_beats_benchmark": average > baseline,
        }
    return {
        "schema_version": OUTCOME_SCHEMA,
        "source_checkpoint_sha256": checkpoint.content_sha256,
        "source_checkpoint_recorded_at_utc": checkpoint.recorded_at_utc.isoformat(),
        "source_research_rule": checkpoint.research_rule,
        "evaluated_at_utc": evaluated_at.astimezone(UTC).isoformat(),
        "signal_session": checkpoint.signal_session.isoformat(),
        "entry_session": window.entry_session.isoformat(),
        "exit_session": window.exit_session.isoformat(),
        "holding_sessions": checkpoint.horizon,
        "selected_count": len(checkpoint.shortlist),
        "data_provider": "alpaca",
        "feed": "sip",
        "outcome_adjustment": "split",
        "entry_exit_price_type": "daily_open",
        "benchmark_symbol": BENCHMARK,
        "assumed_cost_bps_each_side": str(cost_bps_per_side),
        "status": status,
        "selected_outcomes": per_stock,
        "benchmark_outcome": benchmark,
        "complete_portfolio_comparison": comparison,
        "warnings": [
            "One prospective observation, not predictive validation or a recommendation.",
            "Outcome-only split adjustment compensates for recorded stock splits; it is NOT an execution fill.",
            "Dividends, delisting proceeds, cash mergers, taxes and market impact are NOT fully handled.",
            "Symmetric trading friction is an assumption, not measured historical bid-ask spreads.",
            "A missing/invalid stock or benchmark prevents ALL portfolio performance claims; no survivorship substitutions.",
            "The frozen universe may include unverified complex security types.",
            "Local checkpoint hashes and timestamps are not independently certified.",
        ],
    }
