"""Large all-market scans use Alpaca's documented 10,000-row page limit."""

from datetime import date

import pytest

from app.market_data.history_client import AlpacaHistoryClient


def test_market_page_limit_is_sent_to_provider(monkeypatch: pytest.MonkeyPatch) -> None:
    client = object.__new__(AlpacaHistoryClient)
    seen: list[dict[str, str]] = []

    def fake_page(params: dict[str, str]) -> dict[str, object]:
        seen.append(dict(params))
        return {"bars": {}, "next_page_token": None}

    monkeypatch.setattr(client, "_get_page", fake_page)
    assert list(client.pages(
        ["AAPL"], start=date(2024, 1, 1), end=date(2024, 1, 10),
        adjustment="all", page_limit=10000,
    )) == [[]]
    assert seen[0]["limit"] == "10000"


def test_market_page_limit_rejects_invalid_sizes() -> None:
    client = object.__new__(AlpacaHistoryClient)
    for invalid in (0, 10001):
        with pytest.raises(ValueError, match="limit"):
            list(client.pages(
                ["AAPL"], start=date(2024, 1, 1), end=date(2024, 1, 10),
                page_limit=invalid,
            ))
