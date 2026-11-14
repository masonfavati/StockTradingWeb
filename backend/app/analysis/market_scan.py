"""Full Alpaca active-tradable US-equity screening, not watchlist ranking.

All prices are completed-day, retrospective `all` adjusted SIP bars, NOT
real-time consolidated quotes or a backtested investment model.
"""

import logging
import re
from collections import defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Protocol
from zoneinfo import ZoneInfo

from app.analysis.opportunities import ResearchCandidate, describe_candidate, shortlist
from app.market_data.asset_search import SearchResult
from app.market_data.history_client import DailyBar, HistoryAdjustment, HistoryFeed
from app.market_data.history_import import completed_session_cutoff

NY = ZoneInfo("America/New_York")
_VALID_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")
logger = logging.getLogger(__name__)
BATCH_SIZE = 60
LOOKBACK_CALENDAR_DAYS = 180


class AssetProvider(Protocol):
    def list_active(self) -> list[SearchResult]: ...


class BarProvider(Protocol):
    def pages(
        self,
        symbols: Sequence[str],
        *,
        start: date,
        end: date | datetime,
        feed: HistoryFeed,
        adjustment: HistoryAdjustment,
        page_limit: int,
    ) -> Iterator[list[DailyBar]]: ...


@dataclass(frozen=True)
class ScanResults:
    directory_size: int
    considered: int
    processed: int
    qualified: int
    latest_session: str | None
    candidates: list[ResearchCandidate]
    excluded_invalid_core_symbols: int = 0
    invalid_core_records: int = 0
    invalid_core_examples: tuple[str, ...] = ()


def scan_market(
    directory: AssetProvider,
    history: BarProvider,
    *,
    now: datetime,
    progress: Callable[[int, int], None],
) -> ScanResults:
    """Scan all active tradable symbols, independently of the user watchlist.

    Partial provider failures fail the whole job. Never silently offer a top-20
    ranking from a subset while claiming market-wide coverage.
    """
    if now.tzinfo is None:
        raise ValueError("Scan time must include a time zone")

    assets = directory.list_active()
    valid = {
        asset.symbol: asset.name
        for asset in assets
        if asset.tradable and _VALID_SYMBOL.fullmatch(asset.symbol) is not None
    }
    symbols = sorted(valid)
    if not symbols:
        raise ValueError("Alpaca returned no eligible active tradable US stocks")
    completed_before = completed_session_cutoff(now=now)
    start = now.astimezone(NY).date() - timedelta(days=LOOKBACK_CALENDAR_DAYS)
    latest_allowed = now.astimezone(NY).date()

    candidates: list[ResearchCandidate] = []
    invalid_symbols: set[str] = set()
    invalid_records = 0
    invalid_examples: list[str] = []

    def on_invalid_core(symbol: str, session_date: date | None, reason: str) -> None:
        nonlocal invalid_records
        invalid_symbols.add(symbol)
        invalid_records += 1
        if len(invalid_examples) < 5:
            invalid_examples.append(f"{symbol} {session_date or 'unknown-date'}: {reason}")

    processed = 0
    most_recent: str | None = None
    for index in range(0, len(symbols), BATCH_SIZE):
        batch = symbols[index : index + BATCH_SIZE]
        grouped: dict[str, list[DailyBar]] = defaultdict(list)
        # Our actual Alpaca client offers a scanner-only quarantine path.
        # Test doubles and other providers retain the existing strict API.
        screening_pages = getattr(history, "screening_pages", None)
        if callable(screening_pages):
            pages = screening_pages(
                batch,
                start=start,
                end=completed_before,
                feed="sip",
                adjustment="all",
                page_limit=10000,
                on_invalid_core=on_invalid_core,
            )
        else:
            pages = history.pages(
                batch,
                start=start,
                end=completed_before,
                feed="sip",
                adjustment="all",
                page_limit=10000,
            )
        for page in pages:
            for bar in page:
                if bar.symbol not in valid:
                    raise ValueError("Unexpected symbol in historical market scan")
                if bar.session_date >= latest_allowed:
                    continue
                grouped[bar.symbol].append(bar)

        for symbol in batch:
            # One damaged core bar invalidates this symbol's entire screening
            # history, even if other pages returned otherwise valid bars.
            if symbol in invalid_symbols:
                continue
            rows = grouped.get(symbol, [])
            item = describe_candidate(symbol, valid[symbol], rows)
            if item is not None:
                candidates.append(item)
                date_string = item.last_session.isoformat()
                if most_recent is None or date_string > most_recent:
                    most_recent = date_string
        processed += len(batch)
        progress(processed, len(symbols))

    # Remove stale symbols so a long-suspended company's old trend isn't
    # presented as a current opportunity. Dates are historical, NOT live.
    if most_recent is not None:
        max_date = datetime.fromisoformat(most_recent).date()
        candidates = [
            item for item in candidates
            if (max_date - item.last_session).days <= 3
        ]
    if invalid_symbols:
        logger.warning(
            "Market screening excluded %d symbol(s) with %d invalid core "
            "OHLCV record(s). Examples: %s",
            len(invalid_symbols), invalid_records, "; ".join(invalid_examples),
        )
    return ScanResults(
        directory_size=len(assets),
        considered=len(symbols),
        processed=processed,
        qualified=len(candidates),
        latest_session=most_recent,
        candidates=shortlist(candidates),
        excluded_invalid_core_symbols=len(invalid_symbols),
        invalid_core_records=invalid_records,
        invalid_core_examples=tuple(invalid_examples),
    )
