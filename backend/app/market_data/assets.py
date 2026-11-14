import json
import ssl
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import certifi

from app.core.config import Settings


@dataclass(frozen=True)
class AssetInfo:
    symbol: str
    name: str
    tradable: bool | None


class AssetNotFoundError(Exception):
    pass


class AssetConfigurationError(Exception):
    pass


class AssetLookupError(Exception):
    pass


class AlpacaAssetLookup:
    def __init__(self, settings: Settings) -> None:
        self.settings = settings

    def get(self, symbol: str) -> AssetInfo:
        key = self.settings.alpaca_api_key_id.strip()
        secret = (
            self.settings.alpaca_api_secret_key
            .get_secret_value()
            .strip()
        )

        if not key or not secret:
            raise AssetConfigurationError(
                "Market-data credentials are not configured."
            )

        request = Request(
            f"https://paper-api.alpaca.markets/v2/assets/{symbol}",
            headers={
                "APCA-API-KEY-ID": key,
                "APCA-API-SECRET-KEY": secret,
                "Accept": "application/json",
            },
        )

        try:
            with urlopen(
                request,
                timeout=10,
                context=ssl.create_default_context(
                    cafile=certifi.where()
                ),
            ) as response:
                payload = json.load(response)

        except HTTPError as exc:
            if exc.code == 404:
                raise AssetNotFoundError(
                    "This stock symbol was not found."
                ) from None

            if exc.code in (401, 403):
                raise AssetConfigurationError(
                    "Alpaca rejected the configured credentials."
                ) from None

            raise AssetLookupError(
                "The stock-information provider could not complete the request."
            ) from exc

        except (URLError, OSError, TimeoutError, ValueError) as exc:
            raise AssetLookupError(
                "Could not retrieve verified stock information."
            ) from exc

        if not isinstance(payload, dict):
            raise AssetLookupError("Invalid provider response.")

        provider_symbol = payload.get("symbol")
        name = payload.get("name")

        if (
            not isinstance(provider_symbol, str)
            or provider_symbol.upper() != symbol
            or not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > 200
        ):
            raise AssetLookupError(
                "The provider returned incomplete stock information."
            )

        if payload.get("class") != "us_equity":
            raise AssetNotFoundError(
                "Only U.S. stocks and ETFs are supported right now."
            )

        if payload.get("status") != "active":
            raise AssetNotFoundError(
                "This stock is not currently active."
            )

        tradable_value = payload.get("tradable")
        tradable = (
            tradable_value
            if isinstance(tradable_value, bool)
            else None
        )

        return AssetInfo(
            symbol=provider_symbol.upper(),
            name=name.strip(),
            tradable=tradable,
        )


def get_asset_lookup() -> AlpacaAssetLookup:
    return AlpacaAssetLookup(Settings())
