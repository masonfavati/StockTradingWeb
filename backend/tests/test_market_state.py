from datetime import UTC, datetime
from decimal import Decimal

from app.market_data.alpaca_stream import Quote, Trade
from app.market_data.state import MarketState


def make_trade(feed: str = "iex") -> Trade:
    return Trade(
        feed="test" if feed == "test" else "iex",
        symbol="FAKEPACA" if feed == "test" else "AAPL",
        price=Decimal("150.25"),
        size=10,
        exchange="V",
        timestamp=datetime.now(UTC).isoformat(),
    )


def test_live_trade_is_recognized() -> None:
    state = MarketState(
        feed="iex",
        symbol="AAPL",
        connection_status="connected",
    )
    state.record(make_trade())

    snapshot = state.snapshot()

    assert snapshot["data_status"] == "live"
    assert snapshot["trade_fresh"] is True
    assert snapshot["latest_trade"]["price"] == "150.25"


def test_simulated_data_never_claims_to_be_live() -> None:
    state = MarketState(
        feed="test",
        symbol="FAKEPACA",
        connection_status="connected",
    )
    state.record(make_trade("test"))

    assert state.snapshot()["data_status"] == "simulated"


def test_disconnected_feed_is_not_fresh() -> None:
    state = MarketState(
        feed="iex",
        symbol="AAPL",
        connection_status="connected",
    )
    state.record(make_trade())
    state.connection_status = "reconnecting"

    assert state.snapshot()["trade_fresh"] is False
    assert state.snapshot()["data_status"] == "stale"


def test_other_symbols_are_ignored() -> None:
    state = MarketState(feed="iex", symbol="MSFT")
    state.record(make_trade())

    assert state.snapshot()["latest_trade"] is None


def test_quote_preserves_bid_and_ask() -> None:
    state = MarketState(
        feed="iex",
        symbol="AAPL",
        connection_status="connected",
    )
    state.record(
        Quote(
            feed="iex",
            symbol="AAPL",
            bid=Decimal("150.20"),
            ask=Decimal("150.30"),
            bid_size=5,
            ask_size=8,
            timestamp=datetime.now(UTC).isoformat(),
        )
    )

    snapshot = state.snapshot()
    assert snapshot["latest_quote"]["bid"] == "150.20"
    assert snapshot["latest_quote"]["ask"] == "150.30"


def test_old_data_is_stale() -> None:
    state = MarketState(
        feed="iex",
        symbol="AAPL",
        connection_status="connected",
    )
    state.record(
        Trade(
            feed="iex",
            symbol="AAPL",
            price=Decimal("150.25"),
            size=10,
            exchange="V",
            timestamp="2020-01-01T12:00:00Z",
        )
    )

    assert state.snapshot()["data_status"] == "stale"
    assert state.snapshot()["trade_fresh"] is False
