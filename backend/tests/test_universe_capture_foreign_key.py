"""Catch snapshot insertion errors with real SQLite foreign keys enabled."""

import sqlite3
from collections.abc import Iterator
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine, event, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.db.base import Base
from app.market_data.universe_history import AssetRecord, capture_universe
from app.models.universe import UniverseAsset, UniverseCapture

OBSERVED_AT = datetime(2026, 11, 14, 21, 15, tzinfo=UTC)
SNAPSHOT_DATE = date(2026, 11, 14)


class Directory:
    def __init__(self, assets: list[AssetRecord]) -> None:
        self.assets = assets
        self.calls = 0

    def list_assets(self) -> list[AssetRecord]:
        self.calls += 1
        return self.assets


def make_asset(number: int, *, status: str = "active") -> AssetRecord:
    return AssetRecord(
        asset_id=str(UUID(int=number)),
        symbol=f"TEST{number}",
        name=f"Test {number}",
        exchange="NASDAQ",
        status=status,
        tradable=status == "active",
    )


@pytest.fixture
def fk_session() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")

    @event.listens_for(engine, "connect")
    def enable_foreign_keys(dbapi_connection: sqlite3.Connection, _connection_record: object) -> None:
        # SQLite defaults foreign-key enforcement to off, unlike PostgreSQL.
        dbapi_connection.execute("PRAGMA foreign_keys=ON")

    Base.metadata.create_all(engine)
    try:
        with Session(engine) as session:
            yield session
    finally:
        engine.dispose()


def test_parent_is_inserted_before_children(fk_session: Session) -> None:
    source = Directory([make_asset(1), make_asset(2, status="inactive")])
    capture, created = capture_universe(fk_session, source, observed_at=OBSERVED_AT)

    assert created
    assert capture.captured_on == SNAPSHOT_DATE
    assert capture.asset_count == 2
    assert fk_session.scalar(select(func.count()).select_from(UniverseCapture)) == 1
    assert fk_session.scalar(select(func.count()).select_from(UniverseAsset)) == 2

    repeated, repeated_created = capture_universe(
        fk_session, source, observed_at=OBSERVED_AT
    )
    assert not repeated_created
    assert repeated.captured_on == SNAPSHOT_DATE
    assert source.calls == 1
    assert fk_session.scalar(select(func.count()).select_from(UniverseAsset)) == 2


def test_asset_constraint_failure_rolls_back_parent_and_children(
    fk_session: Session,
) -> None:
    # Simulate a database-level failure during a snapshot with multiple assets.
    source = Directory([make_asset(1), make_asset(2, status="unsupported")])
    with pytest.raises(IntegrityError):
        capture_universe(fk_session, source, observed_at=OBSERVED_AT)

    fk_session.rollback()
    assert fk_session.scalar(select(func.count()).select_from(UniverseCapture)) == 0
    assert fk_session.scalar(select(func.count()).select_from(UniverseAsset)) == 0

    # A retry after a failed transaction should work and remain complete.
    fixed_source = Directory([make_asset(1), make_asset(2)])
    _, created = capture_universe(fk_session, fixed_source, observed_at=OBSERVED_AT)
    assert created
    assert fk_session.scalar(select(func.count()).select_from(UniverseAsset)) == 2
