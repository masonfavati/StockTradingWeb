from typing import Literal

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    database_url: str

    alpaca_api_key_id: str = ""
    alpaca_api_secret_key: SecretStr = SecretStr("")

    market_data_enabled: bool = False
    market_data_feed: Literal["test", "iex"] = "test"
    market_data_symbol: str = "FAKEPACA"

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )
