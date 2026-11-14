"""Register and monitor prospective research checkpoints; no trades or hindsight picks.

Run `uv run python -m app.analysis.forward_journal_cli --help` for commands.
"""

import argparse
import sys
from pathlib import Path

from app.analysis.forward_evaluation import ForwardEvaluationError
from app.analysis.forward_journal import JournalError, capture, register, status_rows
from app.market_data.history_audit import CalendarError


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="action", required=True)
    add = sub.add_parser("register", help="Pin an existing checkpoint using its original checksum")
    add.add_argument("--dir", required=True, type=Path, help="Private research directory")
    add.add_argument("--record", required=True, type=Path, help="Existing checkpoint JSON")
    add.add_argument("--expect-checksum", required=True, help="Original published checkpoint SHA-256")
    scan = sub.add_parser("capture", help="Scan once per eligible signal/rule/horizon")
    scan.add_argument("--dir", required=True, type=Path, help="Private research directory")
    scan.add_argument("--horizon", type=int, default=20, help="Holding sessions, 1–252")
    show = sub.add_parser("status", help="Read-only maturity overview; never fetch price outcomes")
    show.add_argument("--dir", required=True, type=Path, help="Private research directory")
    args = parser.parse_args()
    try:
        if args.action == "register":
            registered_item, added = register(args.dir, args.record, checksum=args.expect_checksum)
            print("REGISTERED" if added else "ALREADY REGISTERED")
            print(f"Signal: {registered_item.checkpoint.signal_session}; horizon: {registered_item.checkpoint.horizon}")
            print(f"Original SHA-256: {registered_item.expected_sha256}")
            print(f"Checkpoint: {registered_item.record_path}")
            print(f"Journal pin: {registered_item.pin_path}")
        elif args.action == "capture":
            state, item = capture(args.dir, horizon=args.horizon)
            if state == "skipped_late":
                print("SKIPPED: too late for the conservative next-session-open entry rule.")
                print("No scan performed; no research evidence manufactured.")
            elif state == "already_registered":
                print("SKIPPED: this signal/rule/horizon is already registered.")
                assert item is not None
                print(f"Existing checkpoint: {item.record_path}")
            else:
                assert item is not None
                print(f"CAPTURED and registered: {item.record_path}")
                print(f"Original SHA-256: {item.expected_sha256}")
            print("Research only; no orders placed. Not an unattended scheduler.")
        else:
            rows = status_rows(args.dir)
            if not rows:
                print("No prospective checkpoints are registered in this research directory.")
                return
            print("FORWARD RESEARCH JOURNAL (no outcome prices fetched)")
            ready = sum(row.state == "READY" for row in rows)
            for row in rows:
                cp = row.entry.checkpoint
                print(
                    f"  {cp.signal_session}  h={cp.horizon:<3}  {row.state:<7}  "
                    f"future sessions {row.observed}/{row.required}  "
                    f"picks={len(cp.shortlist):<2}  hash={row.entry.expected_sha256[:16]}..."
                )
            print(f"Registered: {len(rows)}; READY: {ready}; PENDING: {len(rows) - ready}")
            print("READY means the horizon elapsed, NOT that prices are available or returns verified.")
            print("Use evaluate_forward_cli with each original checksum to create outcome audits.")
    except (
        JournalError, ForwardEvaluationError, CalendarError, OSError, ValueError
    ) as exc:
        print(f"JOURNAL BLOCKED: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
