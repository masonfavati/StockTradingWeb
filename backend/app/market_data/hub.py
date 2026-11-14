from dataclasses import dataclass, field
from typing import Any

from app.market_data.alpaca_stream import Feed, MarketEvent
from app.market_data.state import MarketState

FREE_STREAM_LIMIT = 30


@dataclass
class MarketHub:
    feed: Feed
    connection_status: str = "disabled"
    error: str | None = None
    states: dict[str, MarketState] = field(default_factory=dict)
    names: dict[str, str] = field(default_factory=dict)
    limited_symbols: list[str] = field(default_factory=list)
    confirmed_symbols: set[str] = field(default_factory=set)

    def select_watchlist(self, rows: list[tuple[str, str]]) -> set[str]:
        if self.feed == "test":
            choices = [("FAKEPACA", "Synthetic test instrument")]
            self.limited_symbols = []
        else:
            choices = sorted({symbol: name for symbol, name in rows}.items())
            self.limited_symbols = [
                symbol for symbol, _ in choices[FREE_STREAM_LIMIT:]
            ]
            choices = choices[:FREE_STREAM_LIMIT]

        previous = self.states
        self.names = dict(choices)
        self.states = {
            symbol: previous.get(symbol, MarketState(feed=self.feed, symbol=symbol))
            for symbol, _ in choices
        }
        self._update_connection_statuses()
        return set(self.states)

    def set_connection(self, status: str, error: str | None = None) -> None:
        self.connection_status = status
        self.error = error
        if status != "connected":
            self.confirmed_symbols.clear()
        self._update_connection_statuses()

    def set_confirmed(self, symbols: set[str]) -> None:
        self.confirmed_symbols = symbols.copy()
        self._update_connection_statuses()

    def _update_connection_statuses(self) -> None:
        for symbol, state in self.states.items():
            state.connection_status = (
                "connected"
                if self.connection_status == "connected"
                and symbol in self.confirmed_symbols
                else "subscribing"
                if self.connection_status == "connected"
                else self.connection_status
            )
            state.error = self.error

    def record(self, event: MarketEvent) -> None:
        state = self.states.get(event.symbol)
        if state is not None:
            state.record(event)

    def primary_snapshot(self) -> dict[str, Any]:
        if self.states:
            return next(iter(self.states.values())).snapshot()
        return MarketState(
            feed=self.feed,
            symbol="NONE",
            connection_status=self.connection_status,
            error=self.error,
        ).snapshot()

    def list_snapshot(self) -> dict[str, Any]:
        return {
            "provider": "alpaca",
            "feed": self.feed,
            "coverage": "synthetic_test" if self.feed == "test" else "iex_only",
            "connection_status": self.connection_status,
            "free_stream_limit": FREE_STREAM_LIMIT,
            "limited_symbols": self.limited_symbols,
            "error": self.error,
            "stocks": [
                {
                    **state.snapshot(),
                    "name": self.names[symbol],
                    "subscription_status": (
                        "confirmed" if symbol in self.confirmed_symbols else "pending"
                    ),
                }
                for symbol, state in self.states.items()
            ],
        }
