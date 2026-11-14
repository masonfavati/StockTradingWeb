import asyncio
import json
import ssl

import certifi
from websockets.asyncio.client import connect

from app.core.config import Settings
from app.market_data.alpaca_stream import (
    ENDPOINTS,
    decode_messages,
    parse_events,
    receive_control,
)
from app.market_data.state import MarketState


async def stream_market_data(
    state: MarketState,
    settings: Settings,
) -> None:
    key = settings.alpaca_api_key_id.strip()
    secret = settings.alpaca_api_secret_key.get_secret_value().strip()

    if not key or not secret:
        state.connection_status = "missing_credentials"
        return

    delay = 1

    while True:
        try:
            state.connection_status = "connecting"
            state.error = None

            async with connect(
                ENDPOINTS[state.feed],
                ssl=ssl.create_default_context(cafile=certifi.where()),
                open_timeout=10,
                ping_interval=20,
                ping_timeout=20,
            ) as websocket:
                await receive_control(websocket, "connected")

                await websocket.send(
                    json.dumps({
                        "action": "auth",
                        "key": key,
                        "secret": secret,
                    })
                )
                await receive_control(websocket, "authenticated")

                await websocket.send(
                    json.dumps({
                        "action": "subscribe",
                        "trades": [state.symbol],
                        "quotes": [state.symbol],
                    })
                )
                await receive_control(websocket, "subscription")

                state.connection_status = "connected"
                delay = 1

                async for frame in websocket:
                    for message in decode_messages(frame):
                        if message.get("T") == "error":
                            raise RuntimeError(
                                f"Alpaca error {message.get('code')}: "
                                f"{message.get('msg')}"
                            )

                    for event in parse_events(frame, state.feed):
                        state.record(event)

                raise ConnectionError("Alpaca stream closed")

        except asyncio.CancelledError:
            raise
        except Exception as exc:  # noqa: BLE001
            error_message = str(exc)
            state.error = error_message[:200]

            # Authentication, entitlement, and connection-limit
            # failures require intervention rather than rapid retries.
            fatal_codes = ("402", "405", "406", "409")
            if any(
                f"Alpaca error {code}:" in error_message
                for code in fatal_codes
            ):
                state.connection_status = "error"
                return

            state.connection_status = "reconnecting"
            await asyncio.sleep(delay)
            delay = min(delay * 2, 30)
