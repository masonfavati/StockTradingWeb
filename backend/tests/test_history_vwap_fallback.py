"""Vendor VWAP anomalies must not corrupt sound daily OHLCV observations."""

import logging
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.market_data.history_client import HistoricalDataError, parse_daily_page
from app.market_data.history_import import save_history_page
from app.models.historical_bar import HistoricalBar

NORMAL = {
    "t": "2026-08-03T04:00:00Z",
    "o": Decimal("20.15"),
    "h": Decimal("21.25"),
    "l": Decimal("19.75"),
    "c": Decimal("20.95"),
    "v": 101_000,
    "n": 224,
    "vw": Decimal("20.75"),
}


def test_valid_vwap_remains_exact() -> None:
    [bar] = parse_daily_page({"bars": {"ABC": [NORMAL]}}, ["ABC"])
    assert bar.vwap == Decimal("20.75")
    assert bar.close_price == Decimal("20.95")


@pytest.mark.parametrize("missing", [True, False])
def test_missing_or_null_vwap_remains_none(missing: bool) -> None:
    row = {**NORMAL, "vw": None}
    if missing:
        del row["vw"]
    [bar] = parse_daily_page({"bars": {"ABC": [row]}}, ["ABC"])
    assert bar.vwap is None


@pytest.mark.parametrize("bad_vwap", [0, -1, "NaN", "nonsense", [], True])
def test_invalid_non_null_vwap_is_missing_with_warning(
    bad_vwap: object, caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.market_data.history_client"):
        [bar] = parse_daily_page(
            {"bars": {"ABC": [{**NORMAL, "vw": bad_vwap}]}}, ["ABC"]
        )
    assert bar.symbol == "ABC"
    assert bar.session_date == date(2026, 8, 3)
    assert bar.open_price == Decimal("20.15")
    assert bar.close_price == Decimal("20.95")
    assert bar.volume == 101_000
    assert bar.vwap is None
    assert len(caplog.records) == 1
    assert "ABC 2026-08-03" in caplog.text
    assert "saved those VWAP fields as NULL" in caplog.text
    if bad_vwap == "nonsense":
        assert "nonsense" not in caplog.text


def test_multiple_bad_vwaps_are_reported_once_per_page(
    caplog: pytest.LogCaptureFixture,
) -> None:
    with caplog.at_level(logging.WARNING, logger="app.market_data.history_client"):
        parsed = parse_daily_page(
            {"bars": {
                "AAA": [{**NORMAL, "vw": 0}],
                "BBB": [{**NORMAL, "vw": -1}],
                "CCC": [NORMAL],
            }},
            ["AAA", "BBB", "CCC"],
        )
    assert [bar.vwap for bar in parsed] == [None, None, Decimal("20.75")]
    assert len(caplog.records) == 1
    assert "2 unusable VWAP" in caplog.text


@pytest.mark.parametrize(
    "invalid_field,value",
    [("o", 0), ("c", -1), ("h", 18), ("v", -1), ("t", "not a date")],
)
def test_bad_core_prices_volume_or_timestamp_still_rejected(
    invalid_field: str, value: object,
) -> None:
    with pytest.raises(HistoricalDataError):
        parse_daily_page(
            {"bars": {"ABC": [{**NORMAL, invalid_field: value, "vw": 0}]}},
            ["ABC"],
        )


def test_unexpected_symbol_still_rejected() -> None:
    with pytest.raises(HistoricalDataError, match="Unexpected symbol"):
        parse_daily_page({"bars": {"NOT_REQUESTED": [{**NORMAL, "vw": 0}]}}, ["ABC"])


def test_invalid_vwap_persists_as_sql_null_with_original_prices() -> None:
    [bar] = parse_daily_page(
        {"bars": {"ABC": [{**NORMAL, "vw": 0}]}}, ["ABC"]
    )
    engine = create_engine("sqlite+pysqlite:///:memory:")
    try:
        Base.metadata.create_all(engine)
        with Session(engine) as session:
            assert save_history_page(session, [bar], feed="sip") == 1
            saved = session.get(HistoricalBar, {
                "symbol": "ABC",
                "session_date": date(2026, 8, 3),
                "feed": "sip",
                "adjustment": "raw",
            })
            assert saved is not None
            assert saved.vwap is None
            assert saved.close_price == Decimal("20.95")
            assert saved.volume == 101_000
    finally:
        engine.dispose()
