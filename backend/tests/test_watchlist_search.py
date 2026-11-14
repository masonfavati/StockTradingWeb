from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.market_data.asset_search import (
    AlpacaAssetCatalog,
    AssetSearchUnavailable,
    SearchResult,
    get_asset_catalog,
)


class FakeCatalog:
    def search(self, query: str) -> list[SearchResult]:
        if query.casefold() == "error":
            raise AssetSearchUnavailable("Company lookup is unavailable.")
        return [SearchResult(symbol="AAPL", name="Apple Inc.", tradable=True)]


@pytest.fixture
def client(monkeypatch: pytest.MonkeyPatch) -> Iterator[TestClient]:
    monkeypatch.setenv("MARKET_DATA_ENABLED", "false")
    app.dependency_overrides[get_asset_catalog] = FakeCatalog
    try:
        with TestClient(app) as client:
            yield client
    finally:
        app.dependency_overrides.clear()


def test_search_returns_verified_company(client: TestClient) -> None:
    result = client.get("/api/watchlist/search", params={"q": "apple"})
    assert result.status_code == 200
    assert result.json() == [{
        "symbol": "AAPL", "name": "Apple Inc.", "tradable": True,
    }]


def test_search_rejects_short_query(client: TestClient) -> None:
    assert client.get("/api/watchlist/search", params={"q": "a"}).status_code == 422


def test_search_provider_error_is_explicit(client: TestClient) -> None:
    result = client.get("/api/watchlist/search", params={"q": "error"})
    assert result.status_code == 503


def test_catalog_orders_exact_symbols_first(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.market_data import asset_search

    catalog = AlpacaAssetCatalog()
    rows = [
        SearchResult(symbol="AAP", name="Aap Holdings", tradable=True),
        SearchResult(symbol="AAPL", name="Apple Inc.", tradable=True),
        SearchResult(symbol="PAPL", name="Paper Apple", tradable=True),
    ]

    class FakeSettings:
        alpaca_api_key_id = "test-key"

    monkeypatch.setattr(asset_search, "Settings", FakeSettings)
    monkeypatch.setattr(catalog, "_fetch", lambda settings: rows)
    assert catalog.search("aapl")[0].symbol == "AAPL"
