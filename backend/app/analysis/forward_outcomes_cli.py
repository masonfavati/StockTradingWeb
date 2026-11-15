"""Inspect or process registered forward outcomes without hindsight substitutions.

`status` never fetches outcome prices; `evaluate-ready` processes a bounded
number of mature, not-yet-evaluated checkpoints. No trading orders are placed.
"""

import argparse
import sys
from pathlib import Path

from app.analysis.forward_evaluation import ForwardEvaluationError
from app.analysis.forward_journal import JournalError
from app.analysis.forward_outcomes import OutcomeJournalError, evaluate_ready, outcome_status
from app.market_data.history_audit import CalendarError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    actions = parser.add_subparsers(dest="action", required=True)
    for action in ("status", "evaluate-ready"):
        option = actions.add_parser(action)
        option.add_argument("--dir", type=Path, required=True, help="Existing private research directory")
        if action == "evaluate-ready":
            option.add_argument("--limit", type=int, default=1, help="Maximum mature audits, 1–20")
    args = parser.parse_args()
    try:
        directory = args.dir.expanduser().resolve()
        if args.action == "status":
            items = outcome_status(directory)
            print("PROSPECTIVE OUTCOME JOURNAL (no outcome prices fetched)")
            if not items:
                print("No registered checkpoints")
                return
            for item in items:
                cp = item.row.entry.checkpoint
                print(
                    f"  {cp.signal_session}  h={cp.horizon}  {item.state:<12} "
                    f"future={item.row.observed}/{item.row.required}"
                )
                if item.state == "COMPLETE":
                    print(
                        f"    Selected net: {item.selected_return_pct}%  "
                        f"SPY net: {item.benchmark_return_pct}%  "
                        f"excess: {item.excess_percentage_points} percentage points"
                    )
            groups = {key: sum(item.state == key for item in items) for key in (
                "PENDING", "READY", "COMPLETE", "INCOMPLETE", "NO_SELECTION",
            )}
            print("  ".join(f"{key}: {value}" for key, value in groups.items()))
            print("A complete audit is one observation, NOT a validated forecasting strategy.")
        else:
            result = evaluate_ready(directory, limit=args.limit)
            print(
                f"New outcome audits: {len(result.evaluated)}; "
                f"failed: {len(result.failed)}; "
                f"other registered checkpoints: {result.skipped}"
            )
            for item in result.evaluated:
                print(f"  {item.row.entry.checkpoint.signal_session}: {item.state} {item.audit_path}")
                print(f"    Audit SHA-256: {item.audit_sha256}")
            for error in result.failed:
                print(f"  FAILED: {error}", file=sys.stderr)
            if result.failed:
                raise SystemExit(1)
            if not result.evaluated:
                print("No mature, unevaluated checkpoints in the bounded selection; no outcome prices requested.")
            print("Original checkpoints and journal pins were not changed; no orders placed.")
    except (
        OutcomeJournalError, JournalError, ForwardEvaluationError, CalendarError,
        OSError, ValueError,
    ) as exc:
        parser.exit(1, f"OUTCOME JOURNAL BLOCKED: {exc}\n")


if __name__ == "__main__":
    main()
