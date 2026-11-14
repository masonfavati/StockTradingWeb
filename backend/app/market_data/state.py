from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from app.market_data.alpaca_stream import Feed, MarketEvent, Quote, Trade


def age_seconds(timestamp: str | None) -> float | None:
    if timestamp is None:
        return None

    try:
        observed = datetime.fromisoformat(timestamp)
        if observed.tzinfo is None:
            return None
        return (datetime.now(UTC) - observed).total_seconds()
    except ValueError:
        return None


@dataclass
class MarketState:
    feed: Feed
    symbol: str
    connection_status: str = "disabled"
    last_trade: Trade | None = None
    last_quote: Quote | None = None
    received_at: str | None = None
    error: str | None = None

    def record(self, event: MarketEvent) -> None:
        if event.symbol != self.symbol or event.feed != self.feed:
            return

        if isinstance(event, Trade):
            self.last_trade = event
        elif isinstance(event, Quote):
            self.last_quote = event

        self.received_at = datetime.now(UTC).isoformat()

    def snapshot(self) -> dict[str, Any]:
        trade_age = age_seconds(
            self.last_trade.timestamp if self.last_trade else None
        )
        quote_age = age_seconds(
            self.last_quote.timestamp if self.last_quote else None
        )

        def fresh(age: float | None) -> bool:
            return (
                self.connection_status == "connected"
                and age is not None
                and -5 <= age <= 15
            )

        trade_fresh = fresh(trade_age)
        quote_fresh = fresh(quote_age)

        if self.feed == "test":
            data_status = "simulated"
        elif trade_fresh or quote_fresh:
            data_status = "live"
        elif self.last_trade or self.last_quote:
            data_status = "stale"
        else:
            data_status = "awaiting_events"

        return {
            "provider": "alpaca",
            "feed": self.feed,
            "symbol": self.symbol,
            "coverage": (
                "synthetic_test" if self.feed == "test" else "iex_only"
            ),
            "connection_status": self.connection_status,
            "data_status": data_status,
            "trade_fresh": trade_fresh,
            "quote_fresh": quote_fresh,
            "trade_age_seconds": trade_age,
            "quote_age_seconds": quote_age,
            "received_at": self.received_at,
            "error": self.error,
            "latest_trade": (
                {
                    "price": str(self.last_trade.price),
                    "size": self.last_trade.size,
                    "timestamp": self.last_trade.timestamp,
                }
                if self.last_trade else None
            ),
            "latest_quote": (
                {
                    "bid": str(self.last_quote.bid),
                    "ask": str(self.last_quote.ask),
                    "bid_size": self.last_quote.bid_size,
                    "ask_size": self.last_quote.ask_size,
                    "timestamp": self.last_quote.timestamp,
                }
                if self.last_quote else None
            ),
        }
