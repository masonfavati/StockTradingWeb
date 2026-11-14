from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.market_data.assets import (
    AssetInfo,
    AssetNotFoundError,
    get_asset_lookup,
)


class FakeAssetLookup:
    def get(self, symbol: str) -> AssetInfo:
        names = {
            "AAPL": "Apple Inc.",
            "MSFT": "Microsoft Corporation",
            "SPY": "SPDR S&P 500 ETF Trust",
        }

        if symbol not in names:
            raise AssetNotFoundError("This stock symbol was not found.")

        return AssetInfo(
            symbol=symbol,
            name=names[symbol],
            tradable=True,
        )


@pytest.fixture
def client(
    monkeypatch: pytest.MonkeyPatch,
) -> Iterator[TestClient]:
    monkeypatch.setenv("MARKET_DATA_ENABLED", "false")

    engine = create_engine(
        "sqlite+pysqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )

    Base.metadata.create_all(engine)

    test_session_factory = sessionmaker(
        bind=engine,
        expire_on_commit=False,
    )

    def override_db() -> Iterator[Session]:
        with test_session_factory() as session:
            yield session

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_asset_lookup] = FakeAssetLookup

    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
        engine.dispose()


def test_watchlist_starts_empty(client: TestClient) -> None:
    response = client.get("/api/watchlist")

    assert response.status_code == 200
    assert response.json() == []


def test_add_and_list_stock(client: TestClient) -> None:
    response = client.post(
        "/api/watchlist",
        json={"symbol": "AAPL"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "Apple Inc."

    saved = client.get("/api/watchlist").json()

    assert len(saved) == 1
    assert saved[0]["symbol"] == "AAPL"


def test_lowercase_symbol_is_normalized(client: TestClient) -> None:
    response = client.post(
        "/api/watchlist",
        json={"symbol": "msft"},
    )

    assert response.status_code == 201
    assert response.json()["symbol"] == "MSFT"


def test_duplicate_stock_is_rejected(client: TestClient) -> None:
    client.post("/api/watchlist", json={"symbol": "SPY"})

    response = client.post(
        "/api/watchlist",
        json={"symbol": "SPY"},
    )

    assert response.status_code == 409


def test_invalid_symbol_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/watchlist",
        json={"symbol": "INVALID SYMBOL!"},
    )

    assert response.status_code == 422


def test_unknown_stock_is_rejected(client: TestClient) -> None:
    response = client.post(
        "/api/watchlist",
        json={"symbol": "NOTREAL"},
    )

    assert response.status_code == 404


def test_remove_stock(client: TestClient) -> None:
    client.post("/api/watchlist", json={"symbol": "AAPL"})

    response = client.delete("/api/watchlist/AAPL")

    assert response.status_code == 204
    assert client.get("/api/watchlist").json() == []
