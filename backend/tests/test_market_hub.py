from datetime import UTC, datetime
from decimal import Decimal

import pytest

from app.market_data.alpaca_stream import Trade
from app.market_data.hub import MarketHub
from app.market_data.service import process_frame


def test_selects_multiple_saved_stocks() -> None:
    hub = MarketHub(feed="iex")
    selected = hub.select_watchlist(
        [("MSFT", "Microsoft Corporation"), ("AAPL", "Apple Inc.")]
    )
    assert selected == {"MSFT", "AAPL"}
    assert [stock["symbol"] for stock in hub.list_snapshot()["stocks"]] == [
        "AAPL", "MSFT"
    ]


def test_free_limit_is_explicit() -> None:
    hub = MarketHub(feed="iex")
    selected = hub.select_watchlist(
        [(f"S{i:02d}", f"Company {i}") for i in range(32)]
    )
    assert len(selected) == 30
    assert hub.limited_symbols == ["S30", "S31"]


def test_test_feed_only_uses_fakepaca() -> None:
    hub = MarketHub(feed="test")
    assert hub.select_watchlist([("AAPL", "Apple Inc.")]) == {"FAKEPACA"}


def test_no_live_claim_before_subscription_ack() -> None:
    hub = MarketHub(feed="iex")
    hub.select_watchlist([("AAPL", "Apple Inc.")])
    hub.set_connection("connected")
    hub.record(
        Trade(
            feed="iex",
            symbol="AAPL",
            price=Decimal("123.45"),
            size=10,
            exchange="V",
            timestamp=datetime.now(UTC).isoformat(),
        )
    )
    assert hub.primary_snapshot()["data_status"] == "stale"
    hub.set_confirmed({"AAPL"})
    assert hub.primary_snapshot()["data_status"] == "live"
    hub.set_connection("reconnecting")
    assert hub.primary_snapshot()["data_status"] == "stale"


def test_provider_ack_is_parsed() -> None:
    hub = MarketHub(feed="iex")
    frame = '[{"T":"subscription","trades":["AAPL","MSFT"],"quotes":["AAPL","MSFT"]}]'
    assert process_frame(frame, hub) == ({"AAPL", "MSFT"}, {"AAPL", "MSFT"})


def test_subscriptions_change_without_reconnecting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import asyncio
    import json

    from app.market_data import service

    watched = [("AAPL", "Apple Inc.")]
    monkeypatch.setattr(service, "read_saved_stocks", lambda: watched.copy())

    class FakeWebSocket:
        def __init__(self) -> None:
            self.trades: set[str] = set()
            self.quotes: set[str] = set()
            self.messages: list[str] = []
            self.actions: list[str] = []

        async def send(self, frame: str) -> None:
            message = json.loads(frame)
            self.actions.append(message["action"])
            symbols = set(message["trades"])
            if message["action"] == "subscribe":
                self.trades.update(symbols)
                self.quotes.update(symbols)
            elif message["action"] == "unsubscribe":
                self.trades.difference_update(symbols)
                self.quotes.difference_update(symbols)
            self.messages.append(
                json.dumps([{
                    "T": "subscription",
                    "trades": sorted(self.trades),
                    "quotes": sorted(self.quotes),
                }])
            )

        async def recv(self) -> str:
            return self.messages.pop(0)

    async def scenario() -> list[str]:
        hub = MarketHub(feed="iex", connection_status="connected")
        fake = FakeWebSocket()
        await service.sync_subscriptions(fake, hub)  # type: ignore[arg-type]
        assert hub.confirmed_symbols == {"AAPL"}

        watched.append(("MSFT", "Microsoft Corporation"))
        await service.sync_subscriptions(fake, hub)  # type: ignore[arg-type]
        assert hub.confirmed_symbols == {"AAPL", "MSFT"}

        watched.pop(0)
        await service.sync_subscriptions(fake, hub)  # type: ignore[arg-type]
        assert hub.confirmed_symbols == {"MSFT"}
        return fake.actions

    assert asyncio.run(scenario()) == ["subscribe", "subscribe", "unsubscribe"]
