import argparse
import asyncio
import json
import ssl
import sys
from dataclasses import dataclass
from decimal import Decimal
from typing import Any, Literal, cast

import certifi
from websockets.asyncio.client import ClientConnection, connect
from websockets.exceptions import ConnectionClosed

from app.core.config import Settings

Feed = Literal["test", "iex"]

ENDPOINTS: dict[Feed, str] = {
    "test": "wss://stream.data.alpaca.markets/v2/test",
    "iex": "wss://stream.data.alpaca.markets/v2/iex",
}


@dataclass(frozen=True)
class Trade:
    feed: Feed
    symbol: str
    price: Decimal
    size: int
    exchange: str
    timestamp: str


@dataclass(frozen=True)
class Quote:
    feed: Feed
    symbol: str
    bid: Decimal
    ask: Decimal
    bid_size: int
    ask_size: int
    timestamp: str


MarketEvent = Trade | Quote


def decode_messages(frame: str | bytes) -> list[dict[str, Any]]:
    data = json.loads(frame, parse_float=Decimal)

    if not isinstance(data, list) or not all(
        isinstance(item, dict) for item in data
    ):
        raise ValueError("Expected an array of market-data messages")

    return cast(list[dict[str, Any]], data)


def parse_events(frame: str | bytes, feed: Feed) -> list[MarketEvent]:
    events: list[MarketEvent] = []

    for message in decode_messages(frame):
        kind = message.get("T")

        if kind == "t":
            events.append(
                Trade(
                    feed=feed,
                    symbol=str(message["S"]),
                    price=Decimal(str(message["p"])),
                    size=int(message["s"]),
                    exchange=str(message["x"]),
                    timestamp=str(message["t"]),
                )
            )

        elif kind == "q":
            events.append(
                Quote(
                    feed=feed,
                    symbol=str(message["S"]),
                    bid=Decimal(str(message["bp"])),
                    ask=Decimal(str(message["ap"])),
                    bid_size=int(message["bs"]),
                    ask_size=int(message["as"]),
                    timestamp=str(message["t"]),
                )
            )

    return events


def validate_control(frame: str | bytes, expected: str) -> None:
    for message in decode_messages(frame):
        kind = message.get("T")

        if kind == "error":
            code = message.get("code")
            description = message.get("msg")
            raise RuntimeError(f"Alpaca error {code}: {description}")

        if kind == "success" and message.get("msg") == expected:
            return

        if kind == "subscription" and expected == "subscription":
            return

    raise RuntimeError(f"Unexpected Alpaca response; expected {expected}")


async def receive_control(
    websocket: ClientConnection,
    expected: str,
) -> None:
    frame = await asyncio.wait_for(websocket.recv(), timeout=10)
    validate_control(frame, expected)


async def run_stream(feed: Feed, symbol: str) -> None:
    settings = Settings()

    key = settings.alpaca_api_key_id.strip()
    secret = settings.alpaca_api_secret_key.get_secret_value().strip()

    if not key or not secret:
        raise RuntimeError(
            "Missing Alpaca credentials. Configure backend/.env first."
        )

    url = ENDPOINTS[feed]

    print(f"Connecting to Alpaca {feed} feed...")

    async with connect(
        url,
        ssl=ssl.create_default_context(cafile=certifi.where()),
        open_timeout=10,
        ping_interval=20,
        ping_timeout=20,
    ) as websocket:
        await receive_control(websocket, "connected")

        await websocket.send(
            json.dumps(
                {
                    "action": "auth",
                    "key": key,
                    "secret": secret,
                }
            )
        )
        await receive_control(websocket, "authenticated")
        print("Authenticated successfully.")

        await websocket.send(
            json.dumps(
                {
                    "action": "subscribe",
                    "trades": [symbol],
                    "quotes": [symbol],
                }
            )
        )
        await receive_control(websocket, "subscription")

        print(f"Subscribed to {symbol} on {feed}.")
        print("Waiting for events. Press Ctrl+C to stop.")

        async for frame in websocket:
            for message in decode_messages(frame):
                if message.get("T") == "error":
                    raise RuntimeError(
                        f"Alpaca stream error: {message.get('msg')}"
                    )

            for event in parse_events(frame, feed):
                print(event, flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect Alpaca market-data streams"
    )
    parser.add_argument(
        "--feed",
        choices=["test", "iex"],
        default="test",
    )
    parser.add_argument("--symbol")

    args = parser.parse_args()
    feed: Feed = args.feed
    symbol = (args.symbol or (
        "FAKEPACA" if feed == "test" else "AAPL"
    )).upper()

    if feed == "test" and symbol != "FAKEPACA":
        parser.error("The test feed requires FAKEPACA")

    if feed == "iex" and symbol == "FAKEPACA":
        parser.error("FAKEPACA is not a real stock")

    try:
        asyncio.run(run_stream(feed, symbol))
    except KeyboardInterrupt:
        print("\nStream stopped.")
    except (RuntimeError, OSError, TimeoutError, ConnectionClosed) as exc:
        print(f"Stream failed: {exc}", file=sys.stderr)
        raise SystemExit(1) from None


if __name__ == "__main__":
    main()
