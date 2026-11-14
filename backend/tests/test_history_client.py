from datetime import date
from decimal import Decimal

import pytest

from app.market_data.history_client import (
    AlpacaHistoryClient,
    HistoricalDataError,
    normalize_symbols,
    parse_daily_page,
)

RAW_BAR = {
    "t": "2024-01-03T09:00:00Z",
    "o": Decimal("183.01"),
    "h": Decimal("184.123456"),
    "l": Decimal("182.9"),
    "c": Decimal("183.987654"),
    "v": 1234567,
    "n": 500,
    "vw": Decimal("183.923456"),
}


def test_parse_preserves_precision_and_ny_session_date() -> None:
    results = parse_daily_page({"bars": {"AAPL": [RAW_BAR]}}, ["AAPL"])
    assert len(results) == 1
    assert results[0].session_date == date(2024, 1, 3)
    assert results[0].close_price == Decimal("183.987654")
    assert results[0].volume == 1234567


def test_rejects_malformed_price_and_ohlc() -> None:
    with pytest.raises(HistoricalDataError):
        parse_daily_page({"bars": {"AAPL": [{**RAW_BAR, "c": -1}]}}, ["AAPL"])
    with pytest.raises(HistoricalDataError, match="Inconsistent"):
        parse_daily_page({"bars": {"AAPL": [{**RAW_BAR, "h": Decimal(100)}]}}, ["AAPL"])


def test_rejects_unexpected_symbol() -> None:
    with pytest.raises(HistoricalDataError):
        parse_daily_page({"bars": {"MSFT": [RAW_BAR]}}, ["AAPL"])


def test_normalizes_and_validates_symbols() -> None:
    assert normalize_symbols(["msft", " AAPL ", "aapl"]) == ["AAPL", "MSFT"]
    with pytest.raises(ValueError):
        normalize_symbols(["FAKE SYMBOL!"])


def test_pagination_includes_all_symbols_and_catches_repeated_tokens(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object.__new__(AlpacaHistoryClient)
    requests: list[dict[str, str]] = []

    def fake_fetch(params: dict[str, str]) -> dict[str, object]:
        requests.append(dict(params))
        if "page_token" not in params:
            return {"bars": {"AAPL": [RAW_BAR]}, "next_page_token": "next"}
        return {"bars": {"MSFT": [RAW_BAR]}, "next_page_token": None}

    monkeypatch.setattr(client, "_get_page", fake_fetch)
    pages = list(client.pages(["AAPL", "MSFT"], start=date(2024, 1, 1), end=date(2024, 2, 1)))
    assert [page[0].symbol for page in pages] == ["AAPL", "MSFT"]
    assert requests[0]["feed"] == "sip"
    assert requests[0]["adjustment"] == "raw"
    assert requests[0]["asof"] == "-"
    assert requests[1]["page_token"] == "next"

    monkeypatch.setattr(
        client, "_get_page", lambda params: {"bars": {}, "next_page_token": "again"}
    )
    with pytest.raises(HistoricalDataError, match="Repeated"):
        list(client.pages(["AAPL"], start=date(2024, 1, 1), end=date(2024, 2, 1)))
