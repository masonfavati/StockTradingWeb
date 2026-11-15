"""Bounded, non-overwriting outcome processing for the prospective journal.

The existing one-checkpoint evaluator remains the only source of outcome math.
An outcome is never fetched before the journal's calendar marks it READY.
"""

import hashlib
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any

from app.analysis.forward_evaluation import BENCHMARK, OUTCOME_SCHEMA
from app.analysis.forward_journal import JournalEntry, StatusRow, journal_lock, status_rows

# Keep the primary track record on one PREDECLARED cost assumption. Other
# assumptions must be researched separately, not selected after seeing returns.
FIXED_COST_BPS = Decimal(10)
_MAX_AUDIT_BYTES = 1_000_000
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class OutcomeJournalError(ValueError):
    """An existing audit is inconsistent, or a batch operation cannot be trusted."""


@dataclass(frozen=True)
class OutcomeStatus:
    row: StatusRow
    state: str  # PENDING, READY, COMPLETE, INCOMPLETE, NO_SELECTION
    audit_path: Path
    audit_sha256: str | None = None
    selected_return_pct: str | None = None
    benchmark_return_pct: str | None = None
    excess_percentage_points: str | None = None


def audit_path(root: Path, entry: JournalEntry) -> Path:
    """One immutable outcome filename per journal pin (rule, date, horizon)."""
    return root / "outcomes" / entry.pin_path.name


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise OutcomeJournalError(f"Duplicate outcome JSON key: {key}")
        seen[key] = value
    return seen


def _reject_nonfinite(value: str) -> None:
    raise OutcomeJournalError(f"Nonfinite outcome JSON: {value}")


def _read_existing(path: Path, entry: JournalEntry) -> dict[str, Any]:
    """Validate checksum, source identity, frozen protocol, and audit status."""
    if path.is_symlink() or not path.is_file():
        raise OutcomeJournalError(f"Outcome audit is not a regular file: {path}")
    if path.stat().st_size > _MAX_AUDIT_BYTES:
        raise OutcomeJournalError(f"Outcome audit exceeds safety size: {path}")
    try:
        body: Any = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_reject_nonfinite,
        )
    except OutcomeJournalError:
        raise
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise OutcomeJournalError(f"Invalid outcome JSON: {path}") from exc
    if not isinstance(body, dict):
        raise OutcomeJournalError(f"Outcome must be a JSON object: {path}")
    claimed = body.get("content_sha256")
    if not isinstance(claimed, str) or _SHA256.fullmatch(claimed) is None:
        raise OutcomeJournalError(f"Outcome is missing its checksum: {path}")
    unsigned = {key: value for key, value in body.items() if key != "content_sha256"}
    actual = hashlib.sha256(
        json.dumps(unsigned, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if claimed != actual:
        raise OutcomeJournalError(f"Outcome audit checksum mismatch: {path}")
    cp = entry.checkpoint
    state = body.get("status")
    if not isinstance(state, str) or state not in {"complete", "incomplete_outcomes", "no_selection"}:
        raise OutcomeJournalError(f"Unsupported outcome status: {path}")
    if (
        body.get("schema_version") != OUTCOME_SCHEMA
        or body.get("source_checkpoint_sha256") != entry.expected_sha256
        or body.get("source_checkpoint_recorded_at_utc") != cp.recorded_at_utc.isoformat()
        or body.get("source_research_rule") != cp.research_rule
        or body.get("signal_session") != cp.signal_session.isoformat()
        or type(body.get("holding_sessions")) is not int
        or body["holding_sessions"] != cp.horizon
        or type(body.get("selected_count")) is not int
        or body["selected_count"] != len(cp.shortlist)
        or body.get("assumed_cost_bps_each_side") != str(FIXED_COST_BPS)
        or body.get("benchmark_symbol") != BENCHMARK
        or body.get("data_provider") != "alpaca"
        or body.get("feed") != "sip"
        or body.get("outcome_adjustment") != "split"
        or body.get("entry_exit_price_type") != "daily_open"
    ):
        raise OutcomeJournalError(f"Outcome is inconsistent with pinned research: {path}")
    selected = body.get("selected_outcomes")
    reference = body.get("benchmark_outcome")
    if (
        not isinstance(selected, list)
        or len(selected) != len(cp.shortlist)
        or any(
            not isinstance(item, dict)
            or item.get("symbol") != symbol
            or item.get("rank") != rank
            or not isinstance(item.get("status"), str)
            or item["status"] not in {
                "complete", "invalid_core_bar", "duplicate_session_bar",
                "missing_entry_open", "missing_exit_open", "invalid_price",
            }
            for rank, (item, symbol) in enumerate(zip(selected, cp.shortlist, strict=True), start=1)
        )
        or not isinstance(reference, dict)
        or reference.get("symbol") != BENCHMARK
    ):
        raise OutcomeJournalError(f"Outcome selected symbols or benchmark mismatch: {path}")
    if state == "complete":
        if not selected:
            raise OutcomeJournalError(f"Empty shortlist cannot claim a portfolio return: {path}")
        if any(item["status"] != "complete" for item in selected) or reference.get("status") != "complete":
            raise OutcomeJournalError(f"Complete outcome contains missing prices: {path}")
        comparison = body.get("complete_portfolio_comparison")
        if not isinstance(comparison, dict) or not all(
            isinstance(comparison.get(key), str)
            for key in (
                "selected_equal_weight_net_return_pct",
                "benchmark_net_return_pct",
                "excess_vs_benchmark_percentage_points",
            )
        ):
            raise OutcomeJournalError(f"Complete outcome lacks a valid comparison: {path}")
        try:
            selected_value = Decimal(comparison["selected_equal_weight_net_return_pct"])
            benchmark_value = Decimal(comparison["benchmark_net_return_pct"])
            excess_value = Decimal(comparison["excess_vs_benchmark_percentage_points"])
        except InvalidOperation as exc:
            raise OutcomeJournalError(f"Outcome portfolio returns must be numerical: {path}") from exc
        if not all(value.is_finite() for value in (selected_value, benchmark_value, excess_value)):
            raise OutcomeJournalError(f"Outcome portfolio returns must be finite: {path}")
        # The evaluator rounds both the equal-weight average and paired
        # excess independently to 0.0001 percentage points. In a tie, their
        # displayed difference can be ONE last-place unit apart. Reject
        # anything larger; the cumulative report separately recalculates
        # the exact fields from every selected stock's recorded openings.
        if abs(selected_value - benchmark_value - excess_value) > Decimal("0.0001"):
            raise OutcomeJournalError(f"Outcome excess return is inconsistent: {path}")
    elif body.get("complete_portfolio_comparison") is not None:
        raise OutcomeJournalError(f"Incomplete outcome must not claim portfolio returns: {path}")
    return body


def _status(root: Path, row: StatusRow) -> OutcomeStatus:
    path = audit_path(root, row.entry)
    if path.is_symlink():
        raise OutcomeJournalError(f"Outcome destination is a symlink: {path}")
    if not path.exists():
        return OutcomeStatus(row, row.state, path)
    if row.state != "READY":
        raise OutcomeJournalError("Outcome file exists before the registered horizon matured")
    body = _read_existing(path, row.entry)
    outcome_type = body["status"]
    state = {
        "complete": "COMPLETE",
        "incomplete_outcomes": "INCOMPLETE",
        "no_selection": "NO_SELECTION",
    }[outcome_type]
    comparison = body.get("complete_portfolio_comparison")
    return OutcomeStatus(
        row=row,
        state=state,
        audit_path=path,
        audit_sha256=body["content_sha256"],
        selected_return_pct=comparison["selected_equal_weight_net_return_pct"] if comparison else None,
        benchmark_return_pct=comparison["benchmark_net_return_pct"] if comparison else None,
        excess_percentage_points=comparison["excess_vs_benchmark_percentage_points"] if comparison else None,
    )


def outcome_status(root: Path, *, now: datetime | None = None) -> list[OutcomeStatus]:
    """Read-only inventory; calendar can be queried, never outcome prices."""
    output_dir = root / "outcomes"
    if output_dir.is_symlink() or (output_dir.exists() and not output_dir.is_dir()):
        raise OutcomeJournalError("Outcome destination must be an ordinary directory")
    rows = status_rows(root, now=now)
    return [_status(root, row) for row in rows]


@dataclass(frozen=True)
class BatchResult:
    evaluated: tuple[OutcomeStatus, ...]
    failed: tuple[str, ...]
    skipped: int


def evaluate_ready(
    root: Path, *, limit: int = 1, now: datetime | None = None,
) -> BatchResult:
    """Run at most `limit` missing mature audits using the existing evaluator.

    Holds the journal lock across the scan to avoid two workers creating the
    same audit. Individual evaluator failures are reported, never backfilled.
    """
    if type(limit) is not int or not 1 <= limit <= 20:
        raise OutcomeJournalError("Evaluation limit must be between 1 and 20")
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise OutcomeJournalError("Current time must have a time zone")
    with journal_lock(root):
        snapshot = outcome_status(root, now=current)
        candidates = [row for row in snapshot if row.state == "READY"][:limit]
        if not candidates:
            return BatchResult((), (), len(snapshot))
        directory = root / "outcomes"
        directory.mkdir(mode=0o700, exist_ok=True)
        successes: list[OutcomeStatus] = []
        failures: list[str] = []
        for item in candidates:
            entry = item.row.entry
            command = [
                sys.executable, "-m", "app.analysis.evaluate_forward_cli",
                "--record", str(entry.record_path),
                "--expect-checksum", entry.expected_sha256,
                "--out", str(item.audit_path),
                "--cost-bps", str(FIXED_COST_BPS),
            ]
            try:
                done = subprocess.run(command, check=False)
            except OSError as exc:
                failures.append(f"{entry.checkpoint.signal_session}: cannot launch evaluator: {exc}")
                continue
            if done.returncode != 0:
                failures.append(f"{entry.checkpoint.signal_session}: evaluation failed (exit {done.returncode})")
                # If the evaluator partially created a file, leave it in place
                # for manual inspection; never overwrite it on retry.
                continue
            try:
                audited = _status(root, item.row)
                if audited.state not in {"COMPLETE", "INCOMPLETE", "NO_SELECTION"}:
                    raise OutcomeJournalError("Evaluator exited successfully without an outcome file")
                successes.append(audited)
            except (OSError, OutcomeJournalError) as exc:
                failures.append(f"{entry.checkpoint.signal_session}: generated audit could not be verified: {exc}")
        return BatchResult(tuple(successes), tuple(failures), len(snapshot) - len(candidates))
