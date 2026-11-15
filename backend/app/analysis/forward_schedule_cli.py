"""Opt-in macOS schedule for forward research; never makes trades.

Actions: plan (read-only), write-plist (opt-in file only), run-once (gated),
log (read-only). Nothing automatically installs or enables the LaunchAgent.
"""

import argparse
import plistlib
import sys
from pathlib import Path

from app.analysis.forward_journal import JournalError
from app.analysis.forward_outcomes import OutcomeJournalError, evaluate_ready
from app.analysis.forward_schedule import (
    ScheduleError,
    backend_dir,
    default_agent_path,
    make_launch_agent,
    python_interpreter,
    read_attempts,
    save_launch_agent,
    scheduled_capture,
)
from app.market_data.history_audit import CalendarError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    for action in ("plan", "write-plist", "run-once", "log"):
        command = sub.add_parser(action)
        command.add_argument("--dir", required=True, type=Path, help="Existing research directory")
        if action == "run-once":
            command.add_argument("--horizon", default=20, type=int)
        if action == "log":
            command.add_argument("--limit", default=10, type=int)
    args = parser.parse_args()
    try:
        root = args.dir.expanduser().resolve()
        if args.action == "run-once":
            state, entry = scheduled_capture(root, horizon=args.horizon)
            if state == "outside_window":
                print("SKIPPED: outside the 08:00–08:59 America/New_York window; no provider request.")
            else:
                print(f"SCHEDULED RESEARCH: {state.upper()}")
                if entry is not None:
                    print(f"Signal: {entry.checkpoint.signal_session}")
                    print(f"Original checksum: {entry.expected_sha256}")
                print("No orders placed. Missing sessions are never reconstructed.")
                # Run AFTER the morning scan. Only genuinely matured registered
                # outcomes are evaluated, with the existing immutable journal
                # protocol and a fixed maximum of five outcome audits per day.
                # Existing launchd installations get this without plist changes.
                outcomes = evaluate_ready(root, limit=5)
                print(
                    f"Matured outcome audits: {len(outcomes.evaluated)} completed; "
                    f"{len(outcomes.failed)} failed; {outcomes.skipped} other records."
                )
                for failure in outcomes.failed:
                    print(f"OUTCOME EVALUATION FAILED: {failure}", file=sys.stderr)
                if outcomes.failed:
                    raise SystemExit(1)
        elif args.action == "log":
            records = read_attempts(root, limit=args.limit)
            print("Recent scheduler attempts (local, NOT independently timestamp-certified):")
            for attempt in records:
                print(
                    f"  {attempt['attempted_at_utc']}  {attempt['state']} "
                    f"h={attempt['horizon']}  signal={attempt.get('signal_session') or '-'}"
                )
            if not records:
                print("  None recorded")
        else:
            config = make_launch_agent(
                root=root, backend=backend_dir(), interpreter=python_interpreter(),
            )
            output = default_agent_path()
            if args.action == "plan":
                print(plistlib.dumps(config).decode("utf-8"))
                print(f"Proposed file: {output}")
                print("This is a preview. No scheduler is installed or loaded.")
            else:
                if sys.platform != "darwin":
                    raise ScheduleError("LaunchAgents are supported only on macOS")
                save_launch_agent(output, config)
                print(f"Created (not activated): {output}")
                print(f"To activate: launchctl bootstrap gui/$(id -u) '{output}'")
                print(f"To deactivate: launchctl bootout gui/$(id -u) '{output}'")
                print("Hourly wake-up; only 08:00–08:59 New York time can scan.")
                print("Requires an awake Mac and working provider credentials/network.")
    except (ScheduleError, JournalError, OutcomeJournalError, CalendarError,
            OSError, ValueError) as exc:
        print(f"SCHEDULER BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
