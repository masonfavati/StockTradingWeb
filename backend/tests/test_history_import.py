from datetime import UTC, date, datetime
from decimal import Decimal

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.market_data.history_client import DailyBar
from app.market_data.history_import import completed_sessions_only, save_history_page
from app.models.historical_bar import HistoricalBar


def sample_bar(day: date, close: str = "100.00") -> DailyBar:
    return DailyBar(
        symbol="AAPL",
        session_date=day,
        bar_timestamp=datetime(day.year, day.month, day.day, 14, tzinfo=UTC),
        open_price=Decimal("101.00"),
        high_price=Decimal("105.00"),
        low_price=Decimal("99.00"),
        close_price=Decimal(close),
        volume=1000,
        trade_count=100,
        vwap=Decimal("101.00"),
    )


def test_current_session_is_not_saved() -> None:
    today = date(2026, 11, 16)
    complete = completed_sessions_only(
        [sample_bar(date(2026, 11, 13)), sample_bar(today)], today_ny=today
    )
    assert [bar.session_date for bar in complete] == [date(2026, 11, 13)]


def test_import_is_idempotent_and_updates_corrected_vendor_data() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    HistoricalBar.__table__.create(engine)
    with Session(engine) as session:
        save_history_page(session, [sample_bar(date(2024, 1, 3))], feed="sip")
        save_history_page(session, [sample_bar(date(2024, 1, 3), "102.50")], feed="sip")
        count = session.scalar(select(func.count()).select_from(HistoricalBar))
        row = session.get(HistoricalBar, ("AAPL", date(2024, 1, 3), "sip", "raw"))
        assert count == 1
        assert row is not None
        assert row.close_price == Decimal("102.50")
    engine.dispose()
