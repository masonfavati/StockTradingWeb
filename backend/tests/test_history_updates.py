"""Regression tests for incremental raw history and separate adjusted datasets."""

import sys
from datetime import UTC, date, datetime
from decimal import Decimal

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.market_data.history_client import AlpacaHistoryClient, DailyBar
from app.market_data.history_import import (
    incremental_start,
    latest_saved_day,
    save_history_page,
    sync_history,
)
from app.models.historical_bar import HistoricalBar


def sample(day: date, close: str = "100") -> DailyBar:
    return DailyBar(
        symbol="AAPL",
        session_date=day,
        bar_timestamp=datetime(day.year, day.month, day.day, 14, tzinfo=UTC),
        open_price=Decimal(100),
        high_price=Decimal(110),
        low_price=Decimal(90),
        close_price=Decimal(close),
        volume=1000,
        trade_count=100,
        vwap=Decimal(100),
    )


def test_incremental_new_symbol_fetches_from_requested_start() -> None:
    assert incremental_start(requested_start=date(2022, 1, 1), latest_saved=None) == date(
        2022, 1, 1
    )


def test_incremental_overlaps_recent_week() -> None:
    assert incremental_start(
        requested_start=date(2022, 1, 1), latest_saved=date(2026, 11, 13)
    ) == date(2026, 11, 6)


def test_incremental_respects_requested_lower_bound() -> None:
    assert incremental_start(
        requested_start=date(2026, 11, 10), latest_saved=date(2026, 11, 13)
    ) == date(2026, 11, 10)


def test_incremental_rejects_zero_overlap() -> None:
    with pytest.raises(ValueError, match="Overlap"):
        incremental_start(requested_start=date(2022, 1, 1), latest_saved=None, overlap_days=0)


def test_saved_day_uses_exact_symbol_feed_adjustment_and_provider() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    HistoricalBar.__table__.create(engine)
    with Session(engine) as session:
        save_history_page(session, [sample(date(2024, 1, 2))], feed="sip")
        save_history_page(
            session, [sample(date(2024, 1, 5))], feed="iex", adjustment="all"
        )
        assert latest_saved_day(session, symbol="AAPL", feed="sip") == date(2024, 1, 2)
        assert latest_saved_day(session, symbol="AAPL", feed="iex", adjustment="all") == date(
            2024, 1, 5
        )
        assert latest_saved_day(session, symbol="MSFT", feed="sip") is None
        assert latest_saved_day(session, symbol="AAPL", feed="iex") is None
    engine.dispose()


def test_raw_and_all_are_saved_separately_without_overwriting_each_other() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    HistoricalBar.__table__.create(engine)
    day = date(2024, 1, 3)
    with Session(engine) as session:
        save_history_page(session, [sample(day, "100")], feed="sip")
        save_history_page(session, [sample(day, "99")], feed="sip", adjustment="all")
        save_history_page(session, [sample(day, "98")], feed="sip", adjustment="all")
        assert session.scalar(select(func.count()).select_from(HistoricalBar)) == 2
        raw = session.get(HistoricalBar, ("AAPL", day, "sip", "raw"))
        adjusted = session.get(HistoricalBar, ("AAPL", day, "sip", "all"))
        assert raw is not None and raw.close_price == Decimal(100)
        assert adjusted is not None and adjusted.close_price == Decimal(98)
    engine.dispose()


def test_client_uses_explicit_requested_adjustment(monkeypatch: pytest.MonkeyPatch) -> None:
    client = object.__new__(AlpacaHistoryClient)
    seen: list[dict[str, str]] = []

    def fake_page(params: dict[str, str]) -> dict[str, object]:
        seen.append(dict(params))
        return {"bars": {}, "next_page_token": None}

    monkeypatch.setattr(client, "_get_page", fake_page)
    list(client.pages(["AAPL"], start=date(2024, 1, 1), end=date(2024, 1, 5), adjustment="all"))
    assert seen[0]["adjustment"] == "all"
    assert seen[0]["asof"] == "-"


def test_client_rejects_unknown_adjustment() -> None:
    client = object.__new__(AlpacaHistoryClient)
    with pytest.raises(ValueError, match="adjustment"):
        list(client.pages(
            ["AAPL"], start=date(2024, 1, 1), end=date(2024, 1, 5),
            adjustment="unknown",  # type: ignore[arg-type]
        ))


def test_sync_propagates_adjustment_and_does_not_save_today() -> None:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    HistoricalBar.__table__.create(engine)
    saved_calls: list[dict[str, object]] = []

    class Source:
        def pages(self, symbols: list[str], **kwargs: object) -> list[list[DailyBar]]:
            saved_calls.append({"symbols": symbols, **kwargs})
            return [[sample(date(2024, 1, 3)), sample(date(2024, 1, 4))]]

    with Session(engine) as session:
        pages, processed = sync_history(
            session, Source(),  # type: ignore[arg-type]
            symbols=["AAPL"], start=date(2024, 1, 1), end=date(2024, 1, 5),
            feed="sip", today_ny=date(2024, 1, 4), adjustment="split",
        )
        assert (pages, processed) == (1, 1)
        assert saved_calls[0]["adjustment"] == "split"
        assert session.get(HistoricalBar, ("AAPL", date(2024, 1, 3), "sip", "split")) is not None
        assert session.get(HistoricalBar, ("AAPL", date(2024, 1, 4), "sip", "split")) is None
    engine.dispose()


def test_cli_rejects_incremental_adjusted_fetch(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.market_data.history_import import main

    monkeypatch.setattr(
        sys, "argv", ["history_import", "sync", "--adjustment", "all", "--incremental"]
    )
    with pytest.raises(SystemExit, match="2"):
        main()
