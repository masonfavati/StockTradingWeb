"""Read-only audit of completed Alpaca SIP raw daily bars.

Usage:
    uv run python -m app.market_data.history_audit

Compares every symbol against the exchange calendar through the last
completed New York day, not merely through the latest saved bar.
"""

import json
import ssl
import sys
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from decimal import Decimal
from itertools import pairwise
from typing import Protocol
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import certifi
from sqlalchemy import select

from app.core.config import Settings
from app.db.session import SessionLocal
from app.market_data.history_import import completed_session_cutoff
from app.models.historical_bar import HistoricalBar

CALENDAR_URL = "https://paper-api.alpaca.markets/v2/calendar"
NY = ZoneInfo("America/New_York")


class CalendarError(Exception):
    """Trading calendar could not be independently verified."""


class PriceRow(Protocol):
    symbol: str
    session_date: date
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int


@dataclass(frozen=True)
class SymbolAudit:
    symbol: str
    saved_days: int
    first_day: date
    last_day: date
    missing_sessions: tuple[date, ...]
    unexpected_sessions: tuple[date, ...]
    invalid_prices: int
    large_moves: tuple[date, ...]

    @property
    def passes(self) -> bool:
        return (
            not self.missing_sessions
            and not self.unexpected_sessions
            and self.invalid_prices == 0
        )


def parse_calendar(payload: object, *, start: date, end: date) -> set[date]:
    """Validate calendar response rather than treating a partial body as success."""
    if not isinstance(payload, list) or not payload:
        raise CalendarError("Market calendar returned no sessions.")
    sessions: set[date] = set()
    for item in payload:
        if not isinstance(item, dict) or not isinstance(item.get("date"), str):
            raise CalendarError("Market calendar response contains invalid entries.")
        try:
            day = date.fromisoformat(item["date"])
        except ValueError as exc:
            raise CalendarError("Market calendar contains an invalid date.") from exc
        if day < start or day > end or day.weekday() >= 5 or day in sessions:
            raise CalendarError("Market calendar returned an unexpected date.")
        sessions.add(day)
    return sessions


def get_market_calendar(*, start: date, end: date, settings: Settings) -> set[date]:
    """Download real exchange sessions with existing free Alpaca credentials."""
    key = settings.alpaca_api_key_id.strip()
    secret = settings.alpaca_api_secret_key.get_secret_value().strip()
    if not key or not secret:
        raise CalendarError("Alpaca credentials are missing from backend/.env.")
    request = Request(
        f"{CALENDAR_URL}?{urlencode({'start': start.isoformat(), 'end': end.isoformat()})}",
        headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        },
    )
    try:
        with urlopen(
            request,
            timeout=30,
            context=ssl.create_default_context(cafile=certifi.where()),
        ) as response:
            payload: object = json.load(response)
    except (OSError, ValueError) as exc:
        raise CalendarError("Unable to verify the Alpaca trading calendar.") from exc
    return parse_calendar(payload, start=start, end=end)


def audit_history(
    records: Iterable[PriceRow], *, expected_sessions: set[date]
) -> list[SymbolAudit]:
    """Check prices, coverage after first observed session, and large raw gaps.

    Newer IPOs are not penalized for dates before their first saved observation.
    First-day coverage must therefore be verified separately using listing data.
    """
    if not expected_sessions:
        raise ValueError("Expected exchange calendar cannot be empty.")
    grouped: dict[str, list[PriceRow]] = defaultdict(list)
    for record in records:
        grouped[record.symbol].append(record)
    if not grouped:
        raise ValueError("No historical SIP raw bars were found to audit.")

    results: list[SymbolAudit] = []
    for symbol, rows in sorted(grouped.items()):
        ordered = sorted(rows, key=lambda row: row.session_date)
        dates = {row.session_date for row in ordered}
        first = ordered[0].session_date
        last = ordered[-1].session_date
        applicable = {day for day in expected_sessions if day >= first}
        invalid = 0
        unusual_moves: list[date] = []
        for row in ordered:
            prices = (
                row.open_price, row.high_price, row.low_price, row.close_price
            )
            if (
                any(not price.is_finite() or price <= 0 for price in prices)
                or row.low_price > row.open_price
                or row.open_price > row.high_price
                or row.low_price > row.close_price
                or row.close_price > row.high_price
                or row.volume < 0
            ):
                invalid += 1
        for previous, current in pairwise(ordered):
            if previous.close_price > 0 and current.close_price.is_finite():
                change = current.close_price / previous.close_price - Decimal(1)
                if abs(change) >= Decimal("0.30"):
                    unusual_moves.append(current.session_date)
        results.append(
            SymbolAudit(
                symbol=symbol,
                saved_days=len(ordered),
                first_day=first,
                last_day=last,
                missing_sessions=tuple(sorted(applicable - dates)),
                unexpected_sessions=tuple(sorted(dates - expected_sessions)),
                invalid_prices=invalid,
                large_moves=tuple(unusual_moves),
            )
        )
    return results


def main() -> None:
    # End at the most recently completed NY calendar day, not max(saved dates).
    cutoff = completed_session_cutoff(now=datetime.now(UTC))
    final_day = cutoff.astimezone(NY).date()
    with SessionLocal() as session:
        rows = list(
            session.scalars(
                select(HistoricalBar)
                .where(
                    HistoricalBar.provider == "alpaca",
                    HistoricalBar.feed == "sip",
                    HistoricalBar.adjustment == "raw",
                )
                .order_by(HistoricalBar.symbol, HistoricalBar.session_date)
            ).all()
        )
    if not rows:
        print("No historical SIP raw records to audit.", file=sys.stderr)
        raise SystemExit(1)
    start = min(row.session_date for row in rows)
    try:
        expected = get_market_calendar(start=start, end=final_day, settings=Settings())
        findings = audit_history(rows, expected_sessions=expected)
    except (CalendarError, ValueError) as exc:
        print(f"Audit cannot be completed: {exc}", file=sys.stderr)
        raise SystemExit(2) from None

    print("HISTORICAL DATA AUDIT — Alpaca SIP raw (not live prices)")
    print(f"Calendar: {start} through {final_day}; {len(expected)} trading sessions")
    passed = True
    for finding in findings:
        print(f"\n{finding.symbol}: {finding.saved_days} recorded days")
        print(f"  Missing sessions: {len(finding.missing_sessions)}")
        print(f"  Unexpected dates: {len(finding.unexpected_sessions)}")
        print(f"  Invalid price/volume records: {finding.invalid_prices}")
        print(f"  Large raw close changes (review only): {len(finding.large_moves)}")
        for day in finding.missing_sessions[:5]:
            print(f"    Missing {day}")
        for day in finding.unexpected_sessions[:5]:
            print(f"    Unexpected {day}")
        for day in finding.large_moves[:5]:
            print(f"    Large move {day}")
        passed &= finding.passes
    if not passed:
        print("\nAUDIT FAILED: review missing/unexpected dates or invalid data.")
        raise SystemExit(1)
    print("\nAUDIT PASSED for checks listed above.")
    print("Note: no proof of correct corporate-action or IPO-adjusted returns.")


if __name__ == "__main__":
    main()
