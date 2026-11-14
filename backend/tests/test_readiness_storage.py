"""Check that coverage only counts Alpaca SIP raw prices for requested symbols."""

from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.analysis.readiness_cli import load_observed_dates
from app.db.base import Base
from app.models.historical_bar import HistoricalBar


def bar(symbol: str, day: date, *, adjustment: str = "raw", feed: str = "sip") -> HistoricalBar:
    return HistoricalBar(
        symbol=symbol,
        session_date=day,
        provider="alpaca",
        feed=feed,
        adjustment=adjustment,
        bar_timestamp=datetime(2026, 11, 12, 16, tzinfo=UTC),
        open_price=Decimal(100),
        high_price=Decimal(101),
        low_price=Decimal(99),
        close_price=Decimal(100),
        volume=1000,
        trade_count=10,
        vwap=None,
    )


def test_storage_query_excludes_adj_history_and_other_symbols() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        first = date(2026, 11, 12)
        second = date(2026, 11, 13)
        session.add_all([
            bar("ABC", first),
            bar("ABC", second, adjustment="all"),
            bar("XYZ", first),
            bar("ABC", second, feed="iex"),
        ])
        session.commit()
        result = load_observed_dates(session, ["ABC"], first, second)
        assert result == {"ABC": {first}}
    engine.dispose()


def test_empty_sample_does_not_query_database() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    with Session(engine) as session:
        assert load_observed_dates(session, [], date(2026, 1, 1), date(2026, 2, 1)) == {}
    engine.dispose()
