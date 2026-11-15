"""Report cumulative prospective research outcomes without fetching price bars.

Only complete, checksum-validated journal outcomes enter descriptive returns.
Missing outcomes and date-overlap warnings remain visible. No orders placed.
"""

import argparse
import json
from pathlib import Path

from app.analysis.forward_evaluation import ForwardEvaluationError
from app.analysis.forward_journal import JournalError
from app.analysis.forward_outcomes import OutcomeJournalError
from app.analysis.forward_performance import PerformanceReportError, build_performance_report
from app.market_data.history_audit import CalendarError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dir", type=Path, required=True, help="Private research journal directory")
    parser.add_argument("--json", action="store_true", help="Emit the same read-only report as machine JSON")
    args = parser.parse_args()
    try:
        report = build_performance_report(args.dir.expanduser().resolve())
        if args.json:
            print(json.dumps(report, indent=2, sort_keys=True))
            return
        print("CUMULATIVE FORWARD RESEARCH (DESCRIPTIVE ONLY — NO NEW PRICES)")
        print("=" * 67)
        print(f"Registered checkpoints: {report['registered_checkpoints']}")
        print("  ".join(f"{state}: {count}" for state, count in report["status_counts"].items()))
        if not report["groups"]:
            print("No frozen checkpoints yet; no performance result exists.")
        for group in report["groups"]:
            print(f"\nRule: {group['research_rule']}")
            print(f"Holding period: {group['holding_sessions']} exchange sessions")
            print(f"Registered: {group['registered_checkpoints']}; " + "  ".join(
                f"{state}: {count}" for state, count in group["status_counts"].items()
            ))
            metrics = group["metrics"]
            if metrics is None:
                print("NO COMPLETE OUTCOMES: no returns, win rates, or comparison reported.")
                continue
            print(f"Completed paired observations: {metrics['complete_windows']}")
            print(f"Mean selected net: {metrics['mean_selected_net_pct']}% | "
                  f"Mean SPY net: {metrics['mean_spy_net_pct']}%")
            print(f"Mean paired excess: {metrics['mean_paired_excess_pp']} pp | "
                  f"Median paired excess: {metrics['median_paired_excess_pp']} pp")
            print(f"Positive selected windows: {metrics['positive_selected_windows']}/{metrics['complete_windows']}; "
                  f"Beat SPY: {metrics['windows_beating_spy']}/{metrics['complete_windows']}")
            print(f"Excess range: {metrics['worst_paired_excess_pp']} to "
                  f"{metrics['best_paired_excess_pp']} pp; "
                  f"descriptive dispersion: {metrics['descriptive_excess_dispersion_pp']} pp")
            overlap = group["overlap"]
            print(f"Overlapping holding windows: {overlap['observations_with_overlap']}/"
                  f"{metrics['complete_windows']}; overlapping pairs: {overlap['overlapping_pairs']}; "
                  f"max simultaneous: {overlap['maximum_simultaneous_windows']}")
            print(f"Maximum calendar-disjoint windows: {overlap['maximum_date_disjoint_windows']} "
                  "(NOT an inferred independent sample size)")
        print("\nLIMITATIONS: averages are not cumulative portfolio profits, Sharpe, CAGR, or proof of skill.")
        print("Missing outcomes remain in the registered counts; no selection/replacement or trade occurs.")
    except (
        PerformanceReportError, OutcomeJournalError, JournalError,
        ForwardEvaluationError, CalendarError, OSError, ValueError,
    ) as exc:
        parser.exit(1, f"PERFORMANCE REPORT BLOCKED: {exc}\n")


if __name__ == "__main__":
    main()
