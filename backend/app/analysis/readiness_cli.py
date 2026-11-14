"""Audit historical research coverage without trading or writing to the database.

Example:
 uv run python -m app.analysis.readiness_cli --snapshot 2026-11-14 \\
   --profile common-name-evidence --start 2026-08-01 --end 2026-11-13 \\
   --offset 0 --limit 100 --horizon 20
"""

import argparse
from collections import defaultdict
from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.analysis.backtest_readiness import ReadinessReport, assess_readiness
from app.core.config import Settings
from app.db.session import SessionLocal
from app.market_data.history_audit import CalendarError, get_market_calendar
from app.market_data.history_import import completed_session_cutoff
from app.market_data.security_profiles import (
    PROFILES,
    ResearchProfile,
    profile_fingerprint,
)
from app.market_data.universe_history import eligible_symbols
from app.models.historical_bar import HistoricalBar
from app.models.universe import UniverseCapture


def load_observed_dates(
    session: Session, symbols: list[str], start: date, end: date,
) -> dict[str, set[date]]:
    """Bound memory using a finite symbol subset and the selected calendar window."""
    if not symbols:
        return {}
    rows = session.execute(
        select(HistoricalBar.symbol, HistoricalBar.session_date)
        .where(
            HistoricalBar.provider == "alpaca",
            HistoricalBar.feed == "sip",
            HistoricalBar.adjustment == "raw",
            HistoricalBar.symbol.in_(symbols),
            HistoricalBar.session_date >= start,
            HistoricalBar.session_date <= end,
        )
    ).all()
    result: dict[str, set[date]] = defaultdict(set)
    for symbol, session_date in rows:
        result[symbol].add(session_date)
    return dict(result)


def print_report(report: ReadinessReport, *, profile: str, universe_total: int, offset: int, fingerprint: str) -> None:
    print("\nMARKET BACKTEST READINESS (DATA AUDIT — NOT A STRATEGY RESULT)")
    print("=" * 67)
    print(f"Snapshot observed: {report.snapshot_date}; research profile: {profile}")
    print(f"Universe: {universe_total} symbols; sampled offset {offset}, count {report.selected_symbols}")
    print(f"Profile fingerprint: {fingerprint}")
    print(f"Independent calendar: {report.start} through {report.end} ({report.trading_sessions} sessions)")
    print(f"Research rule needs {report.required_sessions} sessions (61 lookback + next open + {report.horizon}-session exit)")
    print(f"Sampled symbols with any raw SIP bars: {report.symbols_with_data}/{report.selected_symbols}")
    print(f"Sampled symbols with every calendar session in interval: {report.complete_interval_symbols}")
    print(f"Sampled symbols with unexpected trading dates: {report.unexpected_date_symbols}")
    print(f"Sampled symbols with full trailing 61-session lookback: {report.full_lookback_symbols}")
    print(f"Sampled symbols with >=1 complete replay data window: {report.complete_replay_symbols}")
    if report.earliest_replay_signal is None:
        print("Possible historical replay signals: 0 (date range too short)")
    else:
        print(f"Possible replay signal dates (coverage not guaranteed): {report.earliest_replay_signal} to {report.latest_replay_signal}")
    print(f"Replay signal dates later than snapshot date: {report.point_in_time_replay_dates}")
    print("\nLowest-coverage examples (up to five):")
    for row in sorted(report.entries, key=lambda item: (item.recorded_sessions, item.symbol))[:5]:
        print(f"  {row.symbol}: {row.recorded_sessions}/{report.trading_sessions} sessions")
    print("\nBACKTEST SAFETY GATES")
    if report.point_in_time_replay_dates == 0:
        print("BLOCKED: snapshot was captured AFTER every potential replay signal date, or no replay window exists.")
    else:
        print("CAUTION: snapshot date precedes some signals, but point-in-time prices and security status remain unverified.")
    print("- This is sampled coverage, not validation of the entire market.")
    print("- Names/security types are heuristics; current membership cannot reconstruct past listings or delistings.")
    print("- Raw OHLCV may be retrospectively revised; a snapshot date alone cannot prove point-in-time price availability.")
    print("- Prices omit dividends, split-aware executions, delisting proceeds, spreads, taxes, and market impact.")
    print("- No profitability probability, recommendation, or automatic trade is produced.")


NY = ZoneInfo("America/New_York")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--snapshot", help="Date when directory was captured, YYYY-MM-DD (default: latest)")
    parser.add_argument("--profile", choices=PROFILES, default="common-name-evidence")
    parser.add_argument("--start", required=True, help="First date to audit, YYYY-MM-DD")
    parser.add_argument("--end", help="Last date to audit (defaults to last completed NY session)")
    parser.add_argument("--offset", type=int, default=0)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--horizon", type=int, default=20)
    args = parser.parse_args()
    if args.offset < 0 or not 1 <= args.limit <= 500:
        parser.error("--offset must be >= 0 and --limit must be between 1 and 500")
    if not 1 <= args.horizon <= 252:
        parser.error("--horizon must be between 1 and 252")
    try:
        start = date.fromisoformat(args.start)
        end = date.fromisoformat(args.end) if args.end else completed_session_cutoff(now=datetime.now(UTC)).astimezone(NY).date()
        if end < start:
            raise ValueError("End date must be on or after start date")
        # Prevent requesting future calendar dates when running against a partial day.
        safe_end = completed_session_cutoff(now=datetime.now(UTC)).astimezone(NY).date()
        if end > safe_end:
            raise ValueError("End date is beyond the completed-market-data cutoff")
        with SessionLocal() as session:
            on = date.fromisoformat(args.snapshot) if args.snapshot else session.scalar(
                select(func.max(UniverseCapture.captured_on))
            )
            if on is None or session.get(UniverseCapture, on) is None:
                raise ValueError("No saved universe snapshot for the selected date")
            profile: ResearchProfile = args.profile
            all_symbols = eligible_symbols(session, on, profile=profile)
            sample = all_symbols[args.offset : args.offset + args.limit]
            if not sample:
                raise ValueError("No symbols in selected offset range")
            fingerprint = profile_fingerprint(captured_on=on, profile=profile, symbols=all_symbols)
            observations = load_observed_dates(session, sample, start, end)
        calendar = get_market_calendar(start=start, end=end, settings=Settings())
        report = assess_readiness(sample, observations, calendar, snapshot_date=on, horizon=args.horizon)
    except (ValueError, CalendarError) as exc:
        parser.exit(1, f"Readiness audit stopped safely: {exc}\n")
    print_report(
        report, profile=args.profile, universe_total=len(all_symbols),
        offset=args.offset, fingerprint=fingerprint,
    )


if __name__ == "__main__":
    main()
