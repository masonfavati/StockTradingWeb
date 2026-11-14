from dataclasses import dataclass
from datetime import date
from decimal import Decimal

import pytest

from app.market_data.history_audit import CalendarError, audit_history, parse_calendar


@dataclass(frozen=True)
class SampleBar:
    symbol: str
    session_date: date
    open_price: Decimal = Decimal(100)
    high_price: Decimal = Decimal(105)
    low_price: Decimal = Decimal(95)
    close_price: Decimal = Decimal(100)
    volume: int = 1000


D1 = date(2026, 11, 11)
D2 = date(2026, 11, 12)
D3 = date(2026, 11, 13)


def test_complete_data_passes() -> None:
    result = audit_history(
        [SampleBar("AAPL", D1), SampleBar("AAPL", D2), SampleBar("AAPL", D3)],
        expected_sessions={D1, D2, D3},
    )
    assert len(result) == 1
    assert result[0].passes
    assert result[0].missing_sessions == ()


def test_missing_last_day_is_detected() -> None:
    result = audit_history(
        [SampleBar("AAPL", D1), SampleBar("AAPL", D2)],
        expected_sessions={D1, D2, D3},
    )
    assert result[0].missing_sessions == (D3,)
    assert not result[0].passes


def test_shared_missing_day_is_detected() -> None:
    result = audit_history(
        [SampleBar("AAPL", D1), SampleBar("MSFT", D1)],
        expected_sessions={D1, D2},
    )
    assert all(item.missing_sessions == (D2,) for item in result)


def test_ipo_is_not_penalized_before_first_observed_day() -> None:
    result = audit_history(
        [SampleBar("NEW", D2), SampleBar("NEW", D3)],
        expected_sessions={D1, D2, D3},
    )
    assert result[0].passes


def test_unexpected_weekend_is_detected() -> None:
    result = audit_history(
        [SampleBar("AAPL", D3), SampleBar("AAPL", date(2026, 11, 14))],
        expected_sessions={D3},
    )
    assert result[0].unexpected_sessions == (date(2026, 11, 14),)
    assert not result[0].passes


def test_bad_price_is_detected() -> None:
    row = SampleBar("AAPL", D1, low_price=Decimal(110))
    result = audit_history([row], expected_sessions={D1})
    assert result[0].invalid_prices == 1
    assert not result[0].passes


def test_large_raw_move_is_warning_not_automatic_failure() -> None:
    result = audit_history(
        [SampleBar("AAPL", D1), SampleBar("AAPL", D2, close_price=Decimal(150), high_price=Decimal(155))],
        expected_sessions={D1, D2},
    )
    assert result[0].large_moves == (D2,)
    assert result[0].passes


def test_calendar_parsing_rejects_invalid_values() -> None:
    with pytest.raises(CalendarError):
        parse_calendar([{"date": "2026-11-14"}], start=D1, end=date(2026, 11, 14))
    with pytest.raises(CalendarError):
        parse_calendar([], start=D1, end=D3)


def test_calendar_parsing_accepts_expected_dates() -> None:
    result = parse_calendar([{"date": "2026-11-11"}, {"date": "2026-11-13"}], start=D1, end=D3)
    assert result == {D1, D3}
