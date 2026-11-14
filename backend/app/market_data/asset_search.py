"""Free, cached Alpaca asset-directory search for a beginner-friendly picker."""

import json
import ssl
import time
from dataclasses import dataclass
from threading import Lock
from urllib.error import HTTPError
from urllib.request import Request, urlopen

import certifi

from app.core.config import Settings

ASSETS_URL = (
    "https://paper-api.alpaca.markets/v2/assets"
    "?status=active&asset_class=us_equity"
)
CATALOG_TTL_SECONDS = 60 * 60


class AssetSearchUnavailable(Exception):
    """The legitimate provider directory could not be loaded."""


@dataclass(frozen=True)
class SearchResult:
    symbol: str
    name: str
    tradable: bool


class AlpacaAssetCatalog:
    def __init__(self) -> None:
        self._lock = Lock()
        self._rows: list[SearchResult] = []
        self._loaded_key: str | None = None
        self._expires_at = 0.0

    def _fetch(self, settings: Settings) -> list[SearchResult]:
        key = settings.alpaca_api_key_id.strip()
        secret = settings.alpaca_api_secret_key.get_secret_value().strip()
        if not key or not secret:
            raise AssetSearchUnavailable("Alpaca API credentials are not configured.")

        request = Request(
            ASSETS_URL,
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "Accept": "application/json",
            },
        )
        try:
            with urlopen(
                request,
                timeout=20,
                context=ssl.create_default_context(cafile=certifi.where()),
            ) as response:
                payload = json.load(response)
        except HTTPError as exc:
            if exc.code in (401, 403):
                raise AssetSearchUnavailable(
                    "Alpaca rejected the API credentials. Check backend/.env."
                ) from None
            raise AssetSearchUnavailable("Alpaca's company directory is unavailable.") from exc
        except (OSError, ValueError) as exc:
            raise AssetSearchUnavailable("Alpaca's company directory is unavailable.") from exc

        if not isinstance(payload, list):
            raise AssetSearchUnavailable("Alpaca returned an unexpected directory format.")

        rows: list[SearchResult] = []
        for item in payload:
            if not isinstance(item, dict):
                continue
            symbol, name = item.get("symbol"), item.get("name")
            if (
                item.get("status") != "active"
                or item.get("class") != "us_equity"
                or not isinstance(symbol, str)
                or not isinstance(name, str)
                or not symbol.strip()
                or not name.strip()
            ):
                continue
            rows.append(
                SearchResult(
                    symbol=symbol.strip().upper(),
                    name=name.strip(),
                    tradable=item.get("tradable") is True,
                )
            )
        return rows

    def list_active(self) -> list[SearchResult]:
        """Return Alpaca's full active US-equity directory, not the watchlist.

        The existing search endpoint and scanner share one cached download.
        """
        settings = Settings()
        key = settings.alpaca_api_key_id.strip()
        now = time.monotonic()
        with self._lock:
            if self._loaded_key != key or now >= self._expires_at:
                rows = self._fetch(settings)
                self._rows = rows
                self._loaded_key = key
                self._expires_at = time.monotonic() + CATALOG_TTL_SECONDS
            return list(self._rows)

    def search(self, query: str) -> list[SearchResult]:
        catalog = self.list_active()

        term = query.strip().casefold()
        matches = [
            row for row in catalog
            if term in row.name.casefold() or term in row.symbol.casefold()
        ]

        def sort_key(row: SearchResult) -> tuple[int, str, str]:
            symbol = row.symbol.casefold()
            name = row.name.casefold()
            priority = (
                0 if symbol == term
                else 1 if symbol.startswith(term)
                else 2 if name.startswith(term)
                else 3
            )
            return (priority, name, symbol)

        return sorted(matches, key=sort_key)[:12]


_CATALOG = AlpacaAssetCatalog()


def get_asset_catalog() -> AlpacaAssetCatalog:
    return _CATALOG
