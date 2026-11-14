import asyncio
import json
import ssl

import certifi
from sqlalchemy import select
from websockets.asyncio.client import ClientConnection, connect

from app.core.config import Settings
from app.db.session import SessionLocal
from app.market_data.alpaca_stream import (
    ENDPOINTS,
    decode_messages,
    parse_events,
    receive_control,
)
from app.market_data.hub import MarketHub
from app.models.watchlist import WatchlistEntry


def read_saved_stocks() -> list[tuple[str, str]]:
    with SessionLocal() as session:
        records = session.execute(
            select(WatchlistEntry.symbol, WatchlistEntry.name).order_by(
                WatchlistEntry.symbol
            )
        ).all()
        return [(symbol, name) for symbol, name in records]


def process_frame(
    frame: str | bytes, hub: MarketHub
) -> tuple[set[str], set[str]] | None:
    messages = decode_messages(frame)
    for message in messages:
        if message.get("T") == "error":
            raise RuntimeError(
                f"Alpaca error {message.get('code')}: {message.get('msg')}"
            )

    for event in parse_events(frame, hub.feed):
        hub.record(event)

    for message in messages:
        if message.get("T") == "subscription":
            trades = message.get("trades")
            quotes = message.get("quotes")
            if not isinstance(trades, list) or not isinstance(quotes, list):
                raise ValueError("Invalid subscription acknowledgement")
            if not all(isinstance(s, str) for s in trades + quotes):
                raise ValueError("Invalid subscription symbols")
            return set(trades), set(quotes)
    return None


async def request_change(
    ws: ClientConnection, hub: MarketHub, action: str, symbols: set[str]
) -> None:
    await ws.send(
        json.dumps(
            {"action": action, "trades": sorted(symbols), "quotes": sorted(symbols)}
        )
    )
    expected = (
        hub.confirmed_symbols | symbols
        if action == "subscribe"
        else hub.confirmed_symbols - symbols
    )
    async with asyncio.timeout(10):
        while True:
            response = process_frame(await ws.recv(), hub)
            if response is not None:
                trades, quotes = response
                if trades != expected or quotes != expected:
                    raise RuntimeError("Unexpected provider subscription state")
                hub.set_confirmed(expected)
                return


async def sync_subscriptions(ws: ClientConnection, hub: MarketHub) -> None:
    rows = [] if hub.feed == "test" else await asyncio.to_thread(read_saved_stocks)
    desired = hub.select_watchlist(rows)

    removed = hub.confirmed_symbols - desired
    if removed:
        await request_change(ws, hub, "unsubscribe", removed)

    added = desired - hub.confirmed_symbols
    if added:
        await request_change(ws, hub, "subscribe", added)

    if hub.confirmed_symbols != desired:
        raise RuntimeError("Provider subscriptions do not match the requested stocks")


async def stream_market_data(hub: MarketHub, settings: Settings) -> None:
    key = settings.alpaca_api_key_id.strip()
    secret = settings.alpaca_api_secret_key.get_secret_value().strip()
    if not key or not secret:
        hub.set_connection("missing_credentials", "Alpaca credentials are missing")
        return

    delay = 1
    while True:
        try:
            hub.set_connection("connecting")
            async with connect(
                ENDPOINTS[hub.feed],
                ssl=ssl.create_default_context(cafile=certifi.where()),
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
            ) as websocket:
                await receive_control(websocket, "connected")
                await websocket.send(
                    json.dumps({"action": "auth", "key": key, "secret": secret})
                )
                await receive_control(websocket, "authenticated")
                hub.set_connection("connected")
                delay = 1

                last_sync = float("-inf")
                loop = asyncio.get_running_loop()
                while True:
                    now = loop.time()
                    if now - last_sync >= 2:
                        await sync_subscriptions(websocket, hub)
                        last_sync = loop.time()

                    timeout = max(0.01, 2 - (loop.time() - last_sync))
                    try:
                        frame = await asyncio.wait_for(websocket.recv(), timeout)
                    except TimeoutError:
                        continue
                    response = process_frame(frame, hub)
                    if response is not None:
                        trades, quotes = response
                        hub.set_confirmed(trades & quotes)

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            message = str(exc)[:200]
            if any(f"Alpaca error {code}:" in message for code in (402, 405, 406, 409)):
                hub.set_connection("error", message)
                return
            hub.set_connection("reconnecting", message)
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
