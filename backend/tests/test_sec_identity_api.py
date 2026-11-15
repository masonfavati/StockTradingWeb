"""SEC filer cross-check is opt-in and never contacts SEC during planning."""

import json
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.api import research_dashboard as research
from app.market_data.sec_identity import install_reference

NOW = datetime(2026, 11, 15, 7, tzinfo=UTC)


class FrozenDatetime(datetime):
    @classmethod
    def now(cls, tz=None):  # type: ignore[no-untyped-def]
        return NOW if tz is None else NOW.astimezone(tz)


def client() -> TestClient:
    app = FastAPI()
    app.include_router(research.router)
    return TestClient(app)


def stock_rows() -> SimpleNamespace:
    return SimpleNamespace(
        state="complete", completed_at="2026-11-15T07:00:00+00:00",
        latest_session="2026-11-13",
        candidates=[{
            "symbol": ticker, "name": f"{ticker} Common Stock",
            "last_session": "2026-11-13", "adjusted_close": 25.0,
            "annualized_volatility_pct": 30.0, "drawdown_60d_pct": -7.0,
            "approx_daily_dollar_volume": 10_000_000.0,
        } for ticker in ("AAA", "BBB")],
    )


def test_no_sec_reference_read_unless_requested() -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", stock_rows)
        patch.setattr(research, "load_reference", lambda _root: (_ for _ in ()).throw(
            AssertionError("Not requested")))
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": True,
        })
        assert response.status_code == 200
        assert response.json()["sec_identity_review"] is None
    finally:
        patch.undo()


def test_request_without_source_preserves_cash_and_reasons(tmp_path: Path) -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", stock_rows)
        patch.setattr(research, "_research_root", lambda: tmp_path)
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": True,
            "require_sec_identity": True,
        })
        data = response.json()
        assert response.status_code == 200
        assert data["sec_identity_review"]["status"] == "unavailable"
        assert [r["amount_usd"] for r in data["allocation"]] == ["65.00", "35.00"]
    finally:
        patch.undo()


def test_request_with_imported_sec_data_approves_distinct_filers(tmp_path: Path) -> None:
    path = tmp_path / "source.json"
    path.write_text(json.dumps({
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[1001, "ALPHA INC", "AAA", "Nasdaq"],
                 [1002, "BETA INC", "BBB", "NYSE"]],
    }))
    install_reference(path, tmp_path, now=NOW)
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", stock_rows)
        patch.setattr(research, "_research_root", lambda: tmp_path)
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": True,
            "require_sec_identity": True,
        })
        data = response.json()
        assert response.status_code == 200
        assert [r["amount_usd"] for r in data["allocation"]] == [
            "65.00", "10.00", "10.00", "15.00",
        ]
        assert data["sec_identity_review"]["approved_symbols"] == ["AAA", "BBB"]
        assert len(data["sec_identity_review"]["matches"]) == 2
    finally:
        patch.undo()


def test_sec_request_without_experimental_does_not_read_source() -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", stock_rows)
        patch.setattr(research, "load_reference", lambda _root: (_ for _ in ()).throw(
            AssertionError("No file should be read")))
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100", "allow_experimental_stocks": False,
            "require_sec_identity": True,
        })
        assert response.status_code == 200
        assert response.json()["sec_identity_review"] is None
    finally:
        patch.undo()


def test_both_optional_screens_without_sec_data_never_fetch_history(tmp_path: Path) -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "datetime", FrozenDatetime)
        patch.setattr(research._MANAGER, "snapshot", stock_rows)
        patch.setattr(research, "_research_root", lambda: tmp_path)
        patch.setattr(research, "AlpacaHistoryClient", lambda _settings: (_ for _ in ()).throw(
            AssertionError("SEC rejection should prevent provider request")))
        response = client().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "allow_experimental_stocks": True,
            "require_historical_comovement": True, "require_sec_identity": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["sec_identity_review"]["status"] == "unavailable"
        assert data["comovement_review"]["status"] == "unavailable"
        assert [(row["symbol"], row["amount_usd"]) for row in data["allocation"]] == [
            ("SPY", "65.00"), (None, "35.00"),
        ]
    finally:
        patch.undo()
