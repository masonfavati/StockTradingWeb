"""Check readiness or evaluate a previously frozen prospective market shortlist.

Read-only until the frozen exit session is complete. NEVER modifies the
original checkpoint, ranks new stocks, or places an order.
"""

import argparse
from datetime import UTC, datetime
from datetime import time as dt_time
from decimal import Decimal, InvalidOperation
from pathlib import Path
from zoneinfo import ZoneInfo

from app.analysis.forward_evaluation import (
    BENCHMARK,
    ForwardEvaluationError,
    build_outcome_audit,
    evaluation_window,
    load_checkpoint,
    validate_cost,
)
from app.analysis.forward_record import write_forward_record
from app.core.config import Settings
from app.market_data.history_audit import CalendarError, get_market_calendar
from app.market_data.history_client import AlpacaHistoryClient, DailyBar, HistoricalDataError
from app.market_data.history_import import completed_session_cutoff

NY = ZoneInfo("America/New_York")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--record", type=Path, required=True, help="Frozen forward_*.json checkpoint")
    parser.add_argument("--expect-checksum", required=True, help="SHA-256 from the original scan output")
    parser.add_argument("--out", type=Path, help="New, never-overwritten outcome JSON path")
    parser.add_argument("--status-only", action="store_true", help="Check maturity; never fetch prices or write")
    parser.add_argument("--cost-bps", default="10", help="Predeclared estimated cost, each side (default: 10)")
    args = parser.parse_args()
    if not args.status_only and args.out is None:
        parser.error("--out is required unless --status-only is specified")
    if args.out is not None and not args.out.parent.is_dir():
        parser.error("The output directory must already exist")
    if args.out is not None and args.out.exists():
        parser.error("Refusing to overwrite any existing evaluation")
    try:
        cost_bps = Decimal(args.cost_bps)
        validate_cost(cost_bps)
    except (InvalidOperation, ForwardEvaluationError):
        parser.error("--cost-bps must be a finite number from 0 to 500")
    try:
        checkpoint = load_checkpoint(args.record, expected_checksum=args.expect_checksum)
        now = datetime.now(UTC)
        cutoff = completed_session_cutoff(now=now)
        completed_day = cutoff.astimezone(NY).date()
        if completed_day < checkpoint.signal_session:
            raise ForwardEvaluationError("Current completed-day cutoff precedes the checkpoint")
        settings = Settings()
        sessions = get_market_calendar(
            start=checkpoint.signal_session, end=completed_day, settings=settings,
        )
        window = evaluation_window(checkpoint, sessions=sessions, completed_through=completed_day)
        print(f"Checkpoint verified: {checkpoint.content_sha256}")
        print(f"Frozen signal: {checkpoint.signal_session}; selections: {len(checkpoint.shortlist)}")
        print(f"Holding period: {checkpoint.horizon} exchange sessions after next opening")
        print(
            f"Verified future sessions: {window.observed_future_sessions}/"
            f"{window.required_future_sessions} (completed-data cutoff: {completed_day})"
        )
        if not window.is_mature:
            print("PENDING: frozen exit session has not completed; no price outcomes fetched or saved.")
            return
        assert window.entry_session is not None and window.exit_session is not None
        print(f"Frozen entry open: {window.entry_session}; exit open: {window.exit_session}")
        if args.status_only:
            print("READY for an outcome audit. Status-only: no prices fetched and no file saved.")
            return
        symbols = sorted(set(checkpoint.shortlist) | {BENCHMARK})
        invalid_symbols: set[str] = set()

        def invalid_core(symbol: str, _day: object, _reason: str) -> None:
            invalid_symbols.add(symbol)

        history = AlpacaHistoryClient(settings)
        bars: list[DailyBar] = []
        # Fetch no sessions beyond the frozen exit. A completed day is only
        # eligible after the conservative current cutoff has passed it.
        exit_cutoff = datetime.combine(
            window.exit_session, dt_time(23), tzinfo=NY,
        ).astimezone(UTC)
        if exit_cutoff > cutoff:
            raise ForwardEvaluationError("Exit session is not past the safe SIP cutoff")
        # Split adjustment is for OUTCOMES only, never original signals.
        for page in history.pages(
            symbols, start=window.entry_session, end=exit_cutoff, feed="sip",
            adjustment="split", page_limit=10000, on_invalid_core=invalid_core,
        ):
            bars.extend(
                bar for bar in page
                if bar.session_date in (window.entry_session, window.exit_session)
            )
        body = build_outcome_audit(
            checkpoint, window, bars=bars, invalid_symbols=invalid_symbols,
            cost_bps_per_side=cost_bps, evaluated_at=datetime.now(UTC),
        )
        assert args.out is not None
        digest = write_forward_record(args.out, body)
        print(f"Saved audit: {args.out}")
        print(f"Outcome status: {body['status']}")
        comparison = body["complete_portfolio_comparison"]
        if comparison is not None:
            print(f"Equal-weight selected net return: {comparison['selected_equal_weight_net_return_pct']}%")
            print(f"{BENCHMARK} net return: {comparison['benchmark_net_return_pct']}%")
            print(f"Excess vs {BENCHMARK}: {comparison['excess_vs_benchmark_percentage_points']} percentage points")
        else:
            print("NO COMPLETE PORTFOLIO CLAIM; review incomplete or missing securities in JSON.")
        print(f"Audit SHA-256: {digest}")
        print("Research only; one observation does NOT prove predictive power.")
    except (OSError, ForwardEvaluationError, CalendarError, HistoricalDataError) as exc:
        parser.exit(1, f"EVALUATION BLOCKED: {exc}\n")


if __name__ == "__main__":
    main()
