from fastapi.testclient import TestClient

from app.main import app


def test_market_status_endpoint(monkeypatch) -> None:  # type: ignore[no-untyped-def]
    monkeypatch.setenv("MARKET_DATA_ENABLED", "false")

    with TestClient(app) as client:
        response = client.get("/api/market/status")

    assert response.status_code == 200
    data = response.json()
    assert data["provider"] == "alpaca"
    assert data["connection_status"] == "disabled"
    assert data["latest_trade"] is None
    assert data["data_status"] in {"simulated", "awaiting_events"}
