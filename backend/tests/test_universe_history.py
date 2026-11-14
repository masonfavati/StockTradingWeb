"""Offline tests for dated universe snapshots and bounded raw SIP imports."""

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.market_data.history_client import DailyBar, HistoricalDataError
from app.market_data.universe_history import (
    AssetRecord,
    UniverseDataError,
    backfill_universe,
    capture_universe,
    eligible_symbols,
    parse_asset_directory,
    select_batch_ranges,
)
from app.models.historical_bar import HistoricalBar
from app.models.universe import UniverseAsset, UniverseCapture

OBSERVED_AT = datetime(2026, 11, 14, 21, 15, tzinfo=UTC)
DAY = date(2026, 11, 14)
START = date(2026, 8, 1)


def asset_id(n: int) -> str:
    return str(UUID(int=n))


def asset(
    symbol: str, n: int, *, status: str = "active", tradable: bool = True,
) -> AssetRecord:
    return AssetRecord(asset_id(n), symbol, symbol + " LLC", "NASDAQ", status, tradable)


class Directory:
    def __init__(self, items: list[AssetRecord]) -> None:
        self.items = items
        self.calls = 0

    def list_assets(self) -> list[AssetRecord]:
        self.calls += 1
        return self.items


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        yield db
    engine.dispose()


def test_parser_rejects_empty_directory() -> None:
    with pytest.raises(UniverseDataError, match="empty"):
        parse_asset_directory([])


def test_parser_rejects_wrong_asset_class() -> None:
    with pytest.raises(UniverseDataError, match="asset type"):
        parse_asset_directory([{"class": "crypto"}])


def test_parser_rejects_malformed_provider_identity() -> None:
    with pytest.raises(UniverseDataError, match="Invalid Alpaca asset identity"):
        parse_asset_directory([{
            "id": "not-a-real-uuid", "class": "us_equity", "symbol": "AAPL",
            "name": "Apple", "status": "active", "tradable": True,
            "exchange": "NASDAQ",
        }])


def test_parser_keeps_inactive_assets_and_identity() -> None:
    parsed = parse_asset_directory([
        {"id": asset_id(1), "class": "us_equity", "symbol": "OLD",
         "name": "Inactive Corporation", "status": "inactive", "tradable": False,
         "exchange": "NYSE"},
        {"id": asset_id(2), "class": "us_equity", "symbol": "ABC",
         "name": "Active Corporation", "status": "active", "tradable": True,
         "exchange": "NASDAQ"},
    ])
    assert [row.symbol for row in parsed] == ["ABC", "OLD"]
    assert parsed[1].status == "inactive"
    assert parsed[1].asset_id == asset_id(1)


def test_parser_rejects_duplicate_identities() -> None:
    row = {"id": asset_id(1), "class": "us_equity", "symbol": "ABC",
           "name": "ABC", "status": "active", "tradable": True,
           "exchange": "NASDAQ"}
    with pytest.raises(UniverseDataError, match="Duplicate"):
        parse_asset_directory([row, row])


def test_capture_is_atomic_and_idempotent(session: Session) -> None:
    directory = Directory([asset("ABC", 1), asset("OLD", 2, status="inactive")])
    capture, created = capture_universe(session, directory, observed_at=OBSERVED_AT)
    assert created is True
    assert capture.captured_on == DAY
    assert capture.asset_count == 2
    same, created_again = capture_universe(session, directory, observed_at=OBSERVED_AT)
    assert created_again is False
    assert same.captured_at == capture.captured_at
    assert directory.calls == 1
    assert session.scalar(select(func.count()).select_from(UniverseAsset)) == 2


def test_snapshot_uses_new_york_calendar_date(session: Session) -> None:
    # In winter 02:00 UTC is still the previous calendar day in New York.
    observed = datetime(2026, 11, 15, 2, 0, tzinfo=UTC)
    capture, _ = capture_universe(
        session, Directory([asset("ABC", 1)]), observed_at=observed
    )
    assert capture.captured_on == DAY
    assert capture.captured_at.replace(tzinfo=UTC) == observed  # SQLite drops tzinfo


def test_empty_snapshot_does_not_persist(session: Session) -> None:
    with pytest.raises(UniverseDataError, match="no assets"):
        capture_universe(session, Directory([]), observed_at=OBSERVED_AT)
    assert session.scalar(select(func.count()).select_from(UniverseCapture)) == 0


def test_eligible_stock_selection_excludes_nontradable_or_unknown_syntax(
    session: Session,
) -> None:
    capture_universe(session, Directory([
        asset("XYZ", 1), asset("ABC", 2),
        asset("OLD", 3, status="inactive"),
        asset("NOP", 4, tradable=False),
        asset("XYZ", 5),  # Same ticker, separate stable asset ID.
        asset("WEIRD/SYMBOL", 6),
    ]), observed_at=OBSERVED_AT)
    assert eligible_symbols(session, DAY) == ["ABC", "XYZ"]


def test_select_ranges_are_stable_and_nonoverlapping() -> None:
    symbols = ["A", "B", "C", "D", "E", "F"]
    assert select_batch_ranges(symbols, offset=2, limit=3, batch_size=2) == [
        (2, ["C", "D"]), (4, ["E"]),
    ]
    assert select_batch_ranges(symbols, offset=6, limit=3, batch_size=2) == []


@pytest.mark.parametrize("offset, limit, batch_size", [(-1, 10, 5), (0, 0, 5), (0, 1, 51), (7, 1, 1)])
def test_select_ranges_reject_unsafe_values(offset: int, limit: int, batch_size: int) -> None:
    with pytest.raises(ValueError):
        select_batch_ranges(["A", "B"], offset=offset, limit=limit, batch_size=batch_size)


def bar(symbol: str) -> DailyBar:
    return DailyBar(
        symbol=symbol, session_date=date(2026, 8, 3),
        bar_timestamp=datetime(2026, 8, 3, 14, tzinfo=UTC),
        open_price=Decimal(100), high_price=Decimal(105),
        low_price=Decimal(95), close_price=Decimal(101),
        volume=5000, trade_count=40, vwap=Decimal(100),
    )


class Bars:
    def __init__(self, fail_symbol: str | None = None) -> None:
        self.batches: list[tuple[str, ...]] = []
        self.fail_symbol = fail_symbol

    def pages(
        self, symbols: Sequence[str], *, start: date, end: date | datetime,
        feed: str, adjustment: str,
    ) -> Iterator[list[DailyBar]]:
        assert start == START
        assert feed == "sip"
        assert adjustment == "raw"
        assert isinstance(end, datetime) and end.tzinfo is not None
        self.batches.append(tuple(symbols))
        if self.fail_symbol in symbols:
            raise HistoricalDataError("Simulated provider failure")
        yield [bar(symbol) for symbol in symbols]


def test_bounded_backfill_saves_and_retries_idempotently(session: Session) -> None:
    capture_universe(
        session, Directory([asset("ABC", 1), asset("XYZ", 2), asset("ZZZ", 3)]),
        observed_at=OBSERVED_AT,
    )
    source = Bars()
    kwargs = {
        "captured_on": DAY,
        "start": START,
        "now": OBSERVED_AT,
        "offset": 0,
        "limit": 2,
        "batch_size": 1,
    }
    assert backfill_universe(session, source, **kwargs) == (3, 2, 2, 2)
    assert source.batches == [("ABC",), ("XYZ",)]
    assert backfill_universe(session, source, **kwargs) == (3, 2, 2, 2)
    assert session.scalar(select(func.count()).select_from(HistoricalBar)) == 2


def test_failed_batch_is_reported_without_claiming_completion(session: Session) -> None:
    capture_universe(
        session, Directory([asset("ABC", 1), asset("XYZ", 2)]),
        observed_at=OBSERVED_AT,
    )
    with pytest.raises(UniverseDataError, match="offset 1"):
        backfill_universe(
            session, Bars(fail_symbol="XYZ"), captured_on=DAY,
            start=START, now=OBSERVED_AT, offset=0, limit=2, batch_size=1,
        )
    assert session.scalar(select(func.count()).select_from(HistoricalBar)) == 1


def test_backfill_refuses_missing_snapshot(session: Session) -> None:
    with pytest.raises(ValueError, match="No saved universe snapshot"):
        backfill_universe(
            session, Bars(), captured_on=DAY, start=START,
            now=OBSERVED_AT, offset=0, limit=1, batch_size=1,
        )


def test_backfill_refuses_uncompleted_window(session: Session) -> None:
    capture_universe(session, Directory([asset("ABC", 1)]), observed_at=OBSERVED_AT)
    with pytest.raises(ValueError, match="Start must"):
        backfill_universe(
            session, Bars(), captured_on=DAY, start=date(2026, 11, 14),
            now=OBSERVED_AT, offset=0, limit=1, batch_size=1,
        )
