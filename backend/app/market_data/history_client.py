"""Alpaca free historical stock bars: paginated, source-labelled, raw prices.

Historical SIP is delayed, unlike the separately implemented live IEX stream.
Nothing here is safe to treat as a real-time trading signal.
"""

import json
import logging
import re
import ssl
import time
from collections.abc import Iterator, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from datetime import time as dt_time
from decimal import Decimal, InvalidOperation
from typing import Any, Literal
from urllib.error import HTTPError
from urllib.parse import urlencode
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

import certifi

from app.core.config import Settings

HISTORY_URL = "https://data.alpaca.markets/v2/stocks/bars"
NY = ZoneInfo("America/New_York")
HistoryFeed = Literal["sip", "iex"]
HistoryAdjustment = Literal["raw", "split", "all"]
_SYMBOL_PATTERN = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")
logger = logging.getLogger(__name__)


class HistoricalDataError(Exception):
    """Provider failure or malformed financial data; never substitute guesses."""


@dataclass(frozen=True)
class DailyBar:
    symbol: str
    session_date: date
    bar_timestamp: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal
    volume: int
    trade_count: int | None
    vwap: Decimal | None


def normalize_symbols(symbols: Sequence[str]) -> list[str]:
    result = sorted({symbol.strip().upper() for symbol in symbols})
    if not result:
        raise ValueError("Choose at least one stock to download history for.")
    if any(_SYMBOL_PATTERN.fullmatch(symbol) is None for symbol in result):
        raise ValueError("One or more stock symbols have invalid characters.")
    return result


def _positive_decimal(value: object, field: str) -> Decimal:
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        raise HistoricalDataError(f"Invalid {field} value in provider data.")
    try:
        result = Decimal(str(value))
    except InvalidOperation as exc:
        raise HistoricalDataError(f"Invalid {field} value in provider data.") from exc
    if not result.is_finite() or result <= 0:
        raise HistoricalDataError(f"Invalid {field} value in provider data.")
    return result


def _nonnegative_integer(value: object, field: str) -> int:
    if type(value) is not int or value < 0:
        raise HistoricalDataError(f"Invalid {field} in provider data.")
    return value


def parse_daily_page(payload: object, expected_symbols: Sequence[str]) -> list[DailyBar]:
    """Reject malformed rows rather than inventing or silently dropping prices."""
    if not isinstance(payload, dict) or not isinstance(payload.get("bars"), dict):
        raise HistoricalDataError("The provider returned an unexpected bars response.")

    bars = payload["bars"]
    expected = set(expected_symbols)
    parsed: list[DailyBar] = []
    invalid_vwap_locations: list[str] = []
    for symbol, rows in bars.items():
        if not isinstance(symbol, str) or symbol not in expected or not isinstance(rows, list):
            raise HistoricalDataError("Unexpected symbol or list in provider response.")
        for row in rows:
            if not isinstance(row, dict):
                raise HistoricalDataError("Invalid daily-bar record.")
            try:
                timestamp = datetime.fromisoformat(row["t"])
                open_price = _positive_decimal(row["o"], "open")
                high_price = _positive_decimal(row["h"], "high")
                low_price = _positive_decimal(row["l"], "low")
                close_price = _positive_decimal(row["c"], "close")
                volume = _nonnegative_integer(row["v"], "volume")
                n = row.get("n")
                trade_count = None if n is None else _nonnegative_integer(n, "trade count")
            except (KeyError, TypeError, ValueError, OverflowError) as exc:
                raise HistoricalDataError("Incomplete or invalid daily-bar record.") from exc
            if timestamp.tzinfo is None:
                raise HistoricalDataError("Historical bar timestamp lacks a time zone.")
            if not (
                low_price <= open_price <= high_price
                and low_price <= close_price <= high_price
            ):
                raise HistoricalDataError("Inconsistent OHLC prices in historical data.")
            # VWAP is optional in our storage schema and is not used to derive
            # OHLCV. An unusable vendor VWAP must never be replaced with an
            # estimated price, nor should it discard otherwise sound OHLCV.
            vw = row.get("vw")
            vwap: Decimal | None = None
            if vw is not None:
                try:
                    vwap = _positive_decimal(vw, "VWAP")
                except HistoricalDataError:
                    invalid_vwap_locations.append(
                        f"{symbol} {timestamp.astimezone(NY).date()}"
                    )
            parsed.append(DailyBar(
                symbol=symbol,
                session_date=timestamp.astimezone(NY).date(),
                bar_timestamp=timestamp,
                open_price=open_price,
                high_price=high_price,
                low_price=low_price,
                close_price=close_price,
                volume=volume,
                trade_count=trade_count,
                vwap=vwap,
            ))
    if invalid_vwap_locations:
        # One summary per page: identify affected records without echoing
        # arbitrary provider values or overwhelming logs in a large backfill.
        logger.warning(
            "Alpaca supplied %d unusable VWAP value(s) in a historical page; "
            "saved those VWAP fields as NULL (OHLCV retained). Examples: %s",
            len(invalid_vwap_locations),
            ", ".join(invalid_vwap_locations[:3]),
        )
    return parsed


class AlpacaHistoryClient:
    def __init__(self, settings: Settings, *, min_request_interval: float = 0.45) -> None:
        self.settings = settings
        self.min_request_interval = min_request_interval
        self._last_request_at: float | None = None

    def _get_page(self, params: Mapping[str, str]) -> dict[str, Any]:
        key = self.settings.alpaca_api_key_id.strip()
        secret = self.settings.alpaca_api_secret_key.get_secret_value().strip()
        if not key or not secret:
            raise HistoricalDataError("Alpaca API credentials are missing from backend/.env.")

        # A conservative pace even on large paginated downloads.
        now = time.monotonic()
        if self._last_request_at is not None:
            time.sleep(max(0.0, self.min_request_interval - (now - self._last_request_at)))
        self._last_request_at = time.monotonic()

        request = Request(
            f"{HISTORY_URL}?{urlencode(params)}",
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(
                request,
                timeout=30,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as response:
                payload: object = json.load(response, parse_float=Decimal)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise HistoricalDataError(
                    "Alpaca denied historical access. Check credentials or feed "
                    "entitlements; do not use made-up data."
                ) from None
            if exc.code == 429:
                raise HistoricalDataError(
                    "Alpaca free API rate limit reached. Retry later."
                ) from None
            raise HistoricalDataError(
                f"Alpaca historical request failed (HTTP {exc.code})."
            ) from None
        except (OSError, ValueError) as exc:
            raise HistoricalDataError("Historical market-data request or response failed.") from exc
        if not isinstance(payload, dict):
            raise HistoricalDataError("Alpaca returned an unexpected response format.")
        return payload

    def pages(
        self,
        symbols: Sequence[str],
        *,
        start: date,
        end: date | datetime,
        feed: HistoryFeed = "sip",
        adjustment: HistoryAdjustment = "raw",
        page_limit: int = 1000,
    ) -> Iterator[list[DailyBar]]:
        """End is an explicit UTC cutoff, not a completed-session proof.

        Callers must additionally exclude incomplete New York sessions.
        """
        normalized = normalize_symbols(symbols)
        start_instant = datetime.combine(start, dt_time.min, tzinfo=UTC)
        if isinstance(end, datetime):
            if end.tzinfo is None:
                raise ValueError("The historical end timestamp must have a time zone.")
            end_instant = end.astimezone(UTC)
        else:
            end_instant = datetime.combine(end, dt_time.min, tzinfo=UTC)
        if end_instant <= start_instant:
            raise ValueError("The end timestamp must be after the start date.")
        if feed not in ("sip", "iex"):
            raise ValueError("Unsupported historical feed.")
        if adjustment not in ("raw", "split", "all"):
            raise ValueError("Unsupported historical price adjustment.")
        if not 1 <= page_limit <= 10000:
            raise ValueError("Historical page limit must be between 1 and 10000.")
        params = {
            "symbols": ",".join(normalized),
            "timeframe": "1Day",
            "start": start.isoformat(),
            "end": end_instant.isoformat().replace("+00:00", "Z"),
            "feed": feed,
            "adjustment": adjustment,
            "asof": "-",  # Avoid silently relabelling historic ticker identities.
            "sort": "asc",
            "limit": str(page_limit),
        }
        seen_tokens: set[str] = set()
        while True:
            payload = self._get_page(params)
            yield parse_daily_page(payload, normalized)
            token = payload.get("next_page_token")
            if token is None or token == "":
                return
            if not isinstance(token, str) or token in seen_tokens:
                raise HistoricalDataError("Repeated or invalid pagination token.")
            seen_tokens.add(token)
            params["page_token"] = token
