"""Point-forward Alpaca universe capture and bounded historical RAW backfill.

Usage:
    uv run python -m app.market_data.universe_history capture
    uv run python -m app.market_data.universe_history status
    uv run python -m app.market_data.universe_history backfill --start 2026-08-01 --limit 50

No purchases, predictions, or automatic whole-market database downloads.
"""

import argparse
import json
import re
import ssl
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from urllib.error import HTTPError
from urllib.request import Request, urlopen
from uuid import UUID
from zoneinfo import ZoneInfo

import certifi
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.session import SessionLocal
from app.market_data.history_client import AlpacaHistoryClient, HistoricalDataError
from app.market_data.history_import import completed_session_cutoff, sync_history
from app.market_data.security_profiles import (
    LABELS,
    PROFILES,
    ClassifiedAsset,
    ResearchProfile,
    choose_profile_symbols,
    classify_security,
    label_counts,
    profile_fingerprint,
)
from app.models.universe import UniverseAsset, UniverseCapture

ASSETS_URL = "https://paper-api.alpaca.markets/v2/assets?status=all&asset_class=us_equity"
NY = ZoneInfo("America/New_York")
HISTORY_COMPATIBLE_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")


class UniverseDataError(Exception):
    """The provider directory could not be used safely."""


@dataclass(frozen=True)
class AssetRecord:
    asset_id: str
    symbol: str
    name: str
    exchange: str
    status: str
    tradable: bool


class AssetsProvider(Protocol):
    def list_assets(self) -> list[AssetRecord]: ...


def parse_asset_directory(payload: object) -> list[AssetRecord]:
    """Preserve equities, even if optional display metadata is absent.

    Safety-critical fields (identity, symbol, status, and tradability) must be
    valid. Never silently drop an asset or guess whether it is tradable.
    """
    if not isinstance(payload, list) or not payload:
        raise UniverseDataError("Alpaca returned an empty or malformed asset directory.")
    parsed: list[AssetRecord] = []
    seen_ids: set[str] = set()
    for position, item in enumerate(payload, start=1):
        if not isinstance(item, dict) or item.get("class") != "us_equity":
            raise UniverseDataError(
                f"Unexpected asset type in Alpaca equity directory at entry {position}."
            )
        raw_id = item.get("id")
        symbol = item.get("symbol")
        name = item.get("name")
        exchange = item.get("exchange")
        status = item.get("status")
        tradable = item.get("tradable")
        if not isinstance(raw_id, str):
            raise UniverseDataError(
                f"Malformed Alpaca directory entry {position}: missing asset id; no snapshot saved."
            )
        try:
            asset_id = str(UUID(raw_id))
        except ValueError:
            raise UniverseDataError(
                f"Invalid Alpaca asset identity in directory entry {position}; no snapshot saved."
            ) from None
        if symbol is not None and (not isinstance(symbol, str) or len(symbol) > 64):
            raise UniverseDataError(
                f"Malformed Alpaca directory entry {position}: invalid symbol; no snapshot saved."
            )
        # A missing name/exchange does not alter whether the asset exists.
        # Store the absence as an empty field, never a fictional label.
        if name is not None and not isinstance(name, str):
            raise UniverseDataError(
                f"Malformed Alpaca directory entry {position}: invalid name type; no snapshot saved."
            )
        if exchange is not None and (
            not isinstance(exchange, str) or len(exchange) > 32
        ):
            raise UniverseDataError(
                f"Malformed Alpaca directory entry {position}: invalid exchange; no snapshot saved."
            )
        if status not in ("active", "inactive"):
            raise UniverseDataError(
                f"Malformed Alpaca directory entry {position}: invalid status; no snapshot saved."
            )
        if type(tradable) is not bool:
            raise UniverseDataError(
                f"Malformed Alpaca directory entry {position}: invalid tradable flag; no snapshot saved."
            )
        if asset_id in seen_ids:
            raise UniverseDataError("Duplicate Alpaca asset identity in directory.")
        seen_ids.add(asset_id)
        parsed.append(AssetRecord(
            asset_id=asset_id, symbol=symbol if isinstance(symbol, str) else "",
            name=name.strip() if isinstance(name, str) else "",
            exchange=exchange if isinstance(exchange, str) else "",
            status=status, tradable=tradable,
        ))
    return sorted(parsed, key=lambda item: (item.symbol, item.asset_id))


class AlpacaUniverseClient:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def list_assets(self) -> list[AssetRecord]:
        key = self.settings.alpaca_api_key_id.strip()
        secret = self.settings.alpaca_api_secret_key.get_secret_value().strip()
        if not key or not secret:
            raise UniverseDataError("Alpaca paper credentials are not configured in backend/.env.")
        request = Request(ASSETS_URL, headers={
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
            "Accept": "application/json",
        })
        try:
            with urlopen(
                request, timeout=30,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as response:
                payload: object = json.load(response)
        except HTTPError as exc:
            raise UniverseDataError(
                f"Alpaca asset directory unavailable (HTTP {exc.code}); no snapshot saved."
            ) from None
        except (OSError, ValueError) as exc:
            raise UniverseDataError("Alpaca asset directory request failed; no snapshot saved.") from exc
        assets = parse_asset_directory(payload)
        unknown_symbols = sum(not item.symbol.strip() for item in assets)
        unnamed = sum(not item.name for item in assets)
        unknown_exchange = sum(not item.exchange for item in assets)
        if unknown_symbols or unnamed or unknown_exchange:
            print(
                "Directory metadata missing: "
                f"{unknown_symbols} symbol(s), "
                f"{unnamed} name(s), {unknown_exchange} exchange(s); "
                "retained as unknown, not invented.",
                file=sys.stderr,
            )
        return assets


def capture_universe(
    session: Session, source: AssetsProvider, *, observed_at: datetime | None = None,
) -> tuple[UniverseCapture, bool]:
    """Capture once per NY date, atomically, without historical backdating.

    Live captures use the time *after* the provider responds. In tests, an
    explicit observed_at simulates the provider-receipt time.
    """
    if observed_at is not None and observed_at.tzinfo is None:
        raise ValueError("Observation timestamp requires a time zone.")
    initial_now = observed_at if observed_at is not None else datetime.now(UTC)
    initial_date = initial_now.astimezone(NY).date()
    prior = session.get(UniverseCapture, initial_date)
    if prior is not None:
        return prior, False

    assets = source.list_assets()
    if not assets:
        raise UniverseDataError("The provider returned no assets; refusing empty capture.")
    if len({item.asset_id for item in assets}) != len(assets):
        raise UniverseDataError("Duplicate asset IDs; refusing incomplete capture.")
    receipt_time = observed_at if observed_at is not None else datetime.now(UTC)
    today = receipt_time.astimezone(NY).date()
    # The directory may have been received just after NY midnight.
    prior = session.get(UniverseCapture, today)
    if prior is not None:
        return prior, False
    capture = UniverseCapture(
        captured_on=today, captured_at=receipt_time.astimezone(UTC),
        provider="alpaca", scope="all-status US equities", asset_count=len(assets),
    )
    session.add(capture)
    # No ORM relationship links these models, so SQLAlchemy may otherwise
    # flush child rows first. Persist the parent within this transaction
    # before inserting assets that reference it. This is not a commit.
    session.flush()
    session.add_all([
        UniverseAsset(
            captured_on=today, alpaca_asset_id=item.asset_id,
            symbol=item.symbol, name=item.name, exchange=item.exchange,
            status=item.status, tradable=item.tradable,
        )
        for item in assets
    ])
    session.commit()
    return capture, True


def classified_eligible_assets(
    session: Session, captured_on: date,
) -> list[ClassifiedAsset]:
    """Only status/tradability known at capture; labels use archived names."""
    assets = session.scalars(
        select(UniverseAsset).where(
            UniverseAsset.captured_on == captured_on,
            UniverseAsset.status == "active",
            UniverseAsset.tradable.is_(True),
        )
    ).all()
    return [
        ClassifiedAsset(
            symbol=asset.symbol,
            name=asset.name,
            label=classify_security(asset.symbol, asset.name),
        )
        for asset in assets
        if HISTORY_COMPATIBLE_SYMBOL.fullmatch(asset.symbol)
    ]


def eligible_symbols(
    session: Session, captured_on: date, *, profile: ResearchProfile = "all",
) -> list[str]:
    """A research filter on a *current-at-capture* directory, not historical membership.

    The default 'all' list remains unchanged, so earlier offsets 0-99 stay valid.
    """
    return choose_profile_symbols(
        classified_eligible_assets(session, captured_on), profile=profile
    )


def show_profiles(session: Session, captured_on: date) -> None:
    if session.get(UniverseCapture, captured_on) is None:
        raise ValueError("No saved universe snapshot for that date; run capture first.")
    classified = classified_eligible_assets(session, captured_on)
    counted = label_counts(classified)
    print(f"Research screens for snapshot {captured_on}; name-based heuristics ONLY")
    print(f"Active/tradable/symbol-compatible asset entries: {len(classified)}")
    for label in LABELS:
        examples = sorted({item.symbol for item in classified if item.label == label})[:4]
        suffix = f"; examples: {', '.join(examples)}" if examples else ""
        print(f"  {label}: {counted[label]}{suffix}")
    collisions = len(classified) - len({item.symbol for item in classified})
    print(f"  repeated ticker identities (extra rows): {collisions}")
    for profile in PROFILES:
        symbols = choose_profile_symbols(classified, profile=profile)
        digest = profile_fingerprint(
            captured_on=captured_on, profile=profile, symbols=symbols
        )
        print(f"  profile={profile}: {len(symbols)} symbols; fingerprint={digest}")
    print("'common-name-evidence' means descriptive wording ONLY, NOT verified common shares.")
    print("Unclassified entries may be common shares; excluded items may be investable.")
    print("No historical membership, price suitability, or investment returns are implied.")


def select_batch_ranges(
    symbols: Sequence[str], *, offset: int, limit: int, batch_size: int,
) -> list[tuple[int, list[str]]]:
    if offset < 0 or not 1 <= limit <= 500 or not 1 <= batch_size <= 50:
        raise ValueError("Offset must be >= 0, limit 1–500, batch size 1–50.")
    if offset > len(symbols):
        raise ValueError("Offset exceeds the number of eligible securities.")
    chosen = list(symbols[offset : offset + limit])
    return [(offset + i, chosen[i : i + batch_size]) for i in range(0, len(chosen), batch_size)]


def backfill_universe(
    session: Session, source: AlpacaHistoryClient, *,
    captured_on: date, start: date, now: datetime,
    offset: int, limit: int, batch_size: int,
    profile: ResearchProfile = "all", expected_fingerprint: str | None = None,
) -> tuple[int, int, int, int]:
    """Returns (eligible total, selected count, pages, imported rows).

    Repeating an offset is safe because historical_bars has a natural key.
    Completed batches commit independently; a failed batch must be retried.
    """
    if now.tzinfo is None:
        raise ValueError("Current time must include a time zone.")
    cutoff = completed_session_cutoff(now=now)
    if start < date(2016, 1, 1) or start > cutoff.astimezone(NY).date():
        raise ValueError("Start must be in Alpaca's historical range, before cutoff.")
    if session.get(UniverseCapture, captured_on) is None:
        raise ValueError("No saved universe snapshot for that date; run capture first.")
    symbols = eligible_symbols(session, captured_on, profile=profile)
    fingerprint = profile_fingerprint(
        captured_on=captured_on, profile=profile, symbols=symbols
    )
    if expected_fingerprint is not None and expected_fingerprint != fingerprint:
        raise ValueError(
            f"Profile fingerprint mismatch (current {fingerprint}); "
            "stopping before downloading. Recheck the snapshot, profile and offsets."
        )
    print(f"Research profile: {profile}; fingerprint: {fingerprint}; "
          f"eligible symbols in this profile: {len(symbols)}")
    ranges = select_batch_ranges(symbols, offset=offset, limit=limit, batch_size=batch_size)
    pages_total, rows_total = 0, 0
    for batch_offset, batch in ranges:
        try:
            pages, rows = sync_history(
                session, source, symbols=batch, start=start, end=cutoff,
                feed="sip", adjustment="raw", today_ny=now.astimezone(NY).date(),
            )
        except HistoricalDataError as exc:
            raise UniverseDataError(
                f"Backfill stopped at symbol offset {batch_offset}. "
                "Earlier batches may already be saved; retry this offset. "
                f"Provider error: {exc}"
            ) from None
        pages_total += pages
        rows_total += rows
        print(f"  Offset {batch_offset}: {len(batch)} symbols; {pages} page(s); {rows} bars")
    return len(symbols), sum(len(batch) for _, batch in ranges), pages_total, rows_total


def show_status(session: Session) -> None:
    captures = session.scalars(
        select(UniverseCapture).order_by(UniverseCapture.captured_on.desc()).limit(5)
    ).all()
    if not captures:
        print("No universe snapshots saved yet; run 'capture'.")
        return
    print("Saved Alpaca asset-directory snapshots (observed prospectively):")
    for capture in captures:
        eligible = len(eligible_symbols(session, capture.captured_on))
        print(
            f"  {capture.captured_on}: {capture.asset_count} directory entries, "
            f"{eligible} active/tradable history-compatible symbols; "
            f"observed at {capture.captured_at.isoformat()}"
        )
    count = session.scalar(select(func.count()).select_from(UniverseAsset))
    print(f"Total captured directory rows: {count}")
    print("Historical past membership CANNOT be reconstructed from today's snapshot.")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("action", choices=["capture", "status", "backfill", "profiles"])
    parser.add_argument("--snapshot", help="Saved snapshot NY date; defaults to latest")
    parser.add_argument("--start", help="Backfill starting YYYY-MM-DD (required for backfill)")
    parser.add_argument("--offset", type=int, default=0, help="Starting symbol index, sorted")
    parser.add_argument("--limit", type=int, default=50, help="Max symbols to process, 1–500")
    parser.add_argument("--batch-size", type=int, default=10, help="Symbols/request, 1–50")
    parser.add_argument(
        "--profile", choices=PROFILES, default="all",
        help="Research-name screen; defaults to legacy 'all' offset order",
    )
    parser.add_argument(
        "--expected-fingerprint", help="Abort if the snapshot/profile symbol order changed"
    )
    args = parser.parse_args()
    try:
        with SessionLocal() as session:
            if args.action == "status":
                show_status(session)
                return
            if args.action == "capture":
                capture, created = capture_universe(
                    session, AlpacaUniverseClient(Settings())
                )
                print(
                    f"{'Captured' if created else 'Already captured'} "
                    f"{capture.asset_count} Alpaca equities on {capture.captured_on}."
                )
                print("Snapshots record today's provider state, NOT past membership.")
                return
            if args.action == "backfill" and not args.start:
                parser.error("backfill requires --start YYYY-MM-DD")
            on = date.fromisoformat(args.snapshot) if args.snapshot else session.scalar(
                select(func.max(UniverseCapture.captured_on))
            )
            if on is None:
                parser.error("Capture a universe snapshot first.")
            if args.action == "profiles":
                show_profiles(session, on)
                return
            start = date.fromisoformat(args.start)
            print(
                f"Historical RAW SIP backfill from {start}; "
                f"snapshot from {on} (current-at-capture, NOT past membership)."
            )
            print("Bounded execution; retry an interrupted range without duplicating bars.")
            total, selected, pages, bars = backfill_universe(
                session, AlpacaHistoryClient(Settings()), captured_on=on,
                start=start, now=datetime.now(UTC), offset=args.offset,
                limit=args.limit, batch_size=args.batch_size,
                profile=args.profile, expected_fingerprint=args.expected_fingerprint,
            )
            print(f"Eligible symbols: {total}; selected: {selected}")
            print(f"Downloaded {pages} page(s), processed {bars} raw historical bars.")
            print(f"Next offset for this snapshot AND profile: {args.offset + selected}")
            print("Missing prices remain missing; zero records for an asset are not invented.")
    except (UniverseDataError, HistoricalDataError, ValueError) as exc:
        print(f"Universe history stopped safely: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
