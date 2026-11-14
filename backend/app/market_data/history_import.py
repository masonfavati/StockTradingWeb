"""CLI for free historical stock data, deliberately separate from live signals.

Run:
  uv run python -m app.market_data.history_import sync --start 2022-01-01
  uv run python -m app.market_data.history_import status
"""

import argparse
import sys
from datetime import UTC, date, datetime, timedelta
from datetime import time as dt_time
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import SessionLocal
from app.market_data.history_client import (
    AlpacaHistoryClient,
    DailyBar,
    HistoricalDataError,
    HistoryAdjustment,
    HistoryFeed,
    normalize_symbols,
)
from app.models.historical_bar import HistoricalBar
from app.models.watchlist import WatchlistEntry

NY = ZoneInfo("America/New_York")


def completed_session_cutoff(*, now: datetime) -> datetime:
    """Return a conservative SIP-safe cutoff after the last completed NY day.

    At 23:00 New York time on the previous calendar day, all of that
    day's standard stock-market trading is complete, and the cutoff is
    always at least one hour old. This avoids Alpaca's recent-SIP 403.
    """
    if now.tzinfo is None:
        raise ValueError("The current timestamp must have a time zone.")
    previous_ny_day = now.astimezone(NY).date() - timedelta(days=1)
    return datetime.combine(previous_ny_day, dt_time(23), tzinfo=NY).astimezone(UTC)


def watchlist_symbols(session: Session) -> list[str]:
    return list(session.scalars(select(WatchlistEntry.symbol).order_by(WatchlistEntry.symbol)))


def completed_sessions_only(bars: list[DailyBar], *, today_ny: date) -> list[DailyBar]:
    """Never record today's potentially incomplete daily candle."""
    return [bar for bar in bars if bar.session_date < today_ny]


def save_history_page(
    session: Session,
    bars: list[DailyBar],
    *,
    feed: HistoryFeed,
    adjustment: HistoryAdjustment = "raw",
) -> int:
    """Idempotent upsert using the natural composite key.

    A repeat import can update vendor-corrected raw OHLCV; fetched_at records
    the new fetch time. This is market history, NOT an immutable prediction log.
    """
    fetched_at = datetime.now(UTC)
    for bar in bars:
        row = HistoricalBar(
            symbol=bar.symbol,
            session_date=bar.session_date,
            provider="alpaca",
            feed=feed,
            adjustment=adjustment,
            bar_timestamp=bar.bar_timestamp,
            open_price=bar.open_price,
            high_price=bar.high_price,
            low_price=bar.low_price,
            close_price=bar.close_price,
            volume=bar.volume,
            trade_count=bar.trade_count,
            vwap=bar.vwap,
            fetched_at=fetched_at,
        )
        session.merge(row)
    session.commit()
    return len(bars)


def sync_history(
    session: Session,
    source: AlpacaHistoryClient,
    *,
    symbols: list[str],
    start: date,
    end: date | datetime,
    feed: HistoryFeed,
    today_ny: date,
    adjustment: HistoryAdjustment = "raw",
) -> tuple[int, int]:
    """Returns (vendor pages, rows processed). Pages commit independently."""
    pages = 0
    processed = 0
    for page in source.pages(
        symbols, start=start, end=end, feed=feed, adjustment=adjustment
    ):
        complete_bars = completed_sessions_only(page, today_ny=today_ny)
        processed += save_history_page(
            session, complete_bars, feed=feed, adjustment=adjustment
        )
        pages += 1
    return pages, processed


def latest_saved_day(
    session: Session,
    *,
    symbol: str,
    feed: HistoryFeed,
    adjustment: HistoryAdjustment = "raw",
) -> date | None:
    """Find this symbol's most recent *matching* dataset, not a peer's day."""
    return session.scalar(
        select(func.max(HistoricalBar.session_date)).where(
            HistoricalBar.symbol == symbol,
            HistoricalBar.provider == "alpaca",
            HistoricalBar.feed == feed,
            HistoricalBar.adjustment == adjustment,
        )
    )


def incremental_start(
    *, requested_start: date, latest_saved: date | None, overlap_days: int = 7
) -> date:
    """Overlap a week to pick up vendor corrections and recent missed sessions.

    This isn't a replacement for periodic full refresh and calendar auditing.
    """
    if overlap_days < 1:
        raise ValueError("Overlap must be at least one calendar day.")
    if latest_saved is None:
        return requested_start
    return max(requested_start, latest_saved - timedelta(days=overlap_days))


def show_status(session: Session) -> None:
    rows = session.execute(
        select(
            HistoricalBar.symbol,
            HistoricalBar.feed,
            HistoricalBar.adjustment,
            func.count(),
            func.min(HistoricalBar.session_date),
            func.max(HistoricalBar.session_date),
        )
        .where(HistoricalBar.provider == "alpaca")
        .group_by(
            HistoricalBar.symbol, HistoricalBar.feed, HistoricalBar.adjustment
        )
        .order_by(
            HistoricalBar.symbol, HistoricalBar.feed, HistoricalBar.adjustment
        )
    ).all()
    if not rows:
        print("No historical daily stock records saved yet.")
        return
    print("Saved historical daily bars (not live prices):")
    for symbol, feed, adjustment, count, earliest, latest in rows:
        print(
            f"  {symbol:8} {feed:3} {adjustment:5} "
            f"{count:5} days  {earliest} through {latest}"
        )
    print("'all' is a current-adjustment research series, NOT point-in-time history.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Import free, real daily stock-price history.")
    parser.add_argument("action", choices=["sync", "status"])
    parser.add_argument("--start", help="First date to retrieve (YYYY-MM-DD); default ~5 years ago")
    parser.add_argument(
        "--symbols", help="Comma-separated symbols; otherwise use your saved watchlist"
    )
    parser.add_argument("--feed", choices=["sip", "iex"], default="sip")
    parser.add_argument(
        "--adjustment", choices=["raw", "split", "all"], default="raw",
        help="Historical price basis; 'all' includes splits, dividends, spin-offs",
    )
    parser.add_argument(
        "--incremental", action="store_true",
        help="Fetch only recent raw history with a seven-calendar-day overlap",
    )
    args = parser.parse_args()
    if args.incremental and args.adjustment != "raw":
        parser.error(
            "--incremental requires --adjustment raw. Adjusted historical prices "
            "can change retroactively after corporate actions; refresh them fully."
        )

    with SessionLocal() as session:
        if args.action == "status":
            show_status(session)
            return

        try:
            symbols = normalize_symbols(
                args.symbols.split(",") if args.symbols else watchlist_symbols(session)
            )
            now = datetime.now(UTC)
            end = completed_session_cutoff(now=now)
            start = (
                date.fromisoformat(args.start)
                if args.start
                else end.date() - timedelta(days=5 * 365)
            )
            if start >= end.astimezone(NY).date():
                parser.error("--start must be earlier than the last completed NY session.")
            if start < date(2016, 1, 1):
                parser.error("This importer supports Alpaca history beginning in 2016.")
            feed: HistoryFeed = args.feed
            adjustment: HistoryAdjustment = args.adjustment
            print(f"Historical import: {', '.join(symbols)}")
            print(
                f"Source: Alpaca {feed.upper()} historical, {adjustment} daily bars "
                "(NOT live data)"
            )
            print(f"SIP-safe requested end: {end.isoformat()} (UTC)")
            if adjustment != "raw":
                print(
                    "WARNING: Adjustments use corporate actions known now, and can "
                    "revise old prices. NOT suitable as point-in-time model inputs."
                )
            if args.incremental:
                # Separate requests avoid having one symbol's latest date skip another's.
                totals = [0, 0]
                for symbol in symbols:
                    earliest = incremental_start(
                        requested_start=start,
                        latest_saved=latest_saved_day(
                            session, symbol=symbol, feed=feed, adjustment=adjustment
                        ),
                    )
                    print(f"  {symbol}: fetching since {earliest} (overlap included)")
                    if earliest >= end.astimezone(NY).date():
                        continue
                    pages, processed = sync_history(
                        session, AlpacaHistoryClient(Settings()),
                        symbols=[symbol], start=earliest, end=end,
                        feed=feed, today_ny=now.astimezone(NY).date(),
                        adjustment=adjustment,
                    )
                    totals[0] += pages
                    totals[1] += processed
                print(
                    f"Completed: {totals[0]} page(s); "
                    f"{totals[1]} daily records processed."
                )
            else:
                print(f"Requested full window: {start} through {end.isoformat()} (UTC)")
                pages, processed = sync_history(
                    session, AlpacaHistoryClient(Settings()),
                    symbols=symbols, start=start, end=end, feed=feed,
                    today_ny=now.astimezone(NY).date(), adjustment=adjustment,
                )
                print(f"Completed: {pages} page(s); {processed} daily records processed.")
            print("Run '... history_import status' for distinct days stored.")
        except (HistoricalDataError, ValueError) as exc:
            print(f"Historical import failed safely: {exc}", file=sys.stderr)
            raise SystemExit(1) from None


if __name__ == "__main__":
    main()
