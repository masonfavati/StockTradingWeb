from decimal import Decimal

import pytest

from app.market_data.alpaca_stream import (
    Quote,
    Trade,
    parse_events,
    validate_control,
)


def test_parse_trade_preserves_price_precision() -> None:
    frame = (
        '[{"T":"t","S":"AAPL","p":123.4567,'
        '"s":10,"x":"V","t":"2026-11-13T15:00:00Z"}]'
    )

    events = parse_events(frame, "iex")

    assert len(events) == 1
    assert isinstance(events[0], Trade)
    assert events[0].symbol == "AAPL"
    assert events[0].price == Decimal("123.4567")
    assert events[0].feed == "iex"
    assert events[0].size == 10


def test_parse_quote() -> None:
    frame = (
        '[{"T":"q","S":"AAPL","bp":100.10,'
        '"ap":100.25,"bs":5,"as":7,'
        '"t":"2026-11-13T15:00:00Z"}]'
    )

    events = parse_events(frame, "iex")

    assert len(events) == 1
    assert isinstance(events[0], Quote)
    assert events[0].bid == Decimal("100.10")
    assert events[0].ask == Decimal("100.25")


def test_unknown_events_are_ignored() -> None:
    frame = '[{"T":"b","S":"AAPL","c":100}]'

    assert parse_events(frame, "iex") == []


def test_authentication_success() -> None:
    validate_control(
        '[{"T":"success","msg":"authenticated"}]',
        "authenticated",
    )


def test_provider_error_is_rejected() -> None:
    frame = '[{"T":"error","code":406,"msg":"connection limit exceeded"}]'

    with pytest.raises(RuntimeError, match="406"):
        validate_control(frame, "authenticated")


def test_invalid_message_format_is_rejected() -> None:
    with pytest.raises(ValueError):
        parse_events('{"T":"t"}', "iex")
