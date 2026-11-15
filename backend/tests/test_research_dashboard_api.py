"""Browser planning uses server-origin market data and no unverified outcome figures."""

from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pytest import MonkeyPatch

from app.analysis.forward_journal import register
from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record
from app.api import research_dashboard as research


def make_app() -> TestClient:
    api = FastAPI()
    api.include_router(research.router)
    return TestClient(api)


def test_budget_endpoint_is_research_only_and_does_not_start_scan() -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research._MANAGER, "snapshot", lambda: SimpleNamespace(
            state="idle", completed_at=None, latest_session=None, candidates=[],
        ))
        response = make_app().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "style": "balanced",
        })
        assert response.status_code == 200
        data = response.json()
        assert [row["amount_usd"] for row in data["allocation"]] == ["65.00", "35.00"]
        assert data["experimental_opt_in"] is False
    finally:
        patch.undo()


def test_budget_endpoint_rejects_fractional_cents() -> None:
    response = make_app().post("/api/research/budget-plan", json={
        "budget_usd": "100.001", "style": "growth",
    })
    assert response.status_code == 422


def test_overview_returns_only_verified_report_data() -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research, "_latest_saved_checkpoint", lambda _path: None)
        patch.setattr(research, "build_performance_report", lambda _path: {
            "generated_at_utc": "2026-11-15T00:00:00+00:00",
            "registered_checkpoints": 1,
            "status_counts": {"PENDING": 1, "READY": 0, "COMPLETE": 0},
            "groups": [{"research_rule": "sample", "metrics": None}],
            "warnings": ["No complete outcomes"],
        })
        response = make_app().get("/api/research/overview")
        assert response.status_code == 200
        assert response.json()["groups"][0]["metrics"] is None
        assert response.json()["registered_checkpoints"] == 1
    finally:
        patch.undo()


def test_corrupt_journal_produces_no_partial_report() -> None:
    patch = MonkeyPatch()
    try:
        def fail(_path: object) -> object:
            raise research.JournalError("/secret/path/to/journal")
        patch.setattr(research, "build_performance_report", fail)
        response = make_app().get("/api/research/overview")
        assert response.status_code == 503
        assert "/secret/" not in response.text
        assert "registered_checkpoints" not in response.text
    finally:
        patch.undo()


def test_opt_in_uses_registered_checkpoint_when_browser_has_no_scan() -> None:
    patch = MonkeyPatch()
    try:
        patch.setattr(research._MANAGER, "snapshot", lambda: SimpleNamespace(
            state="idle", completed_at=None, latest_session=None, candidates=[],
        ))
        current = datetime.now(UTC)
        signal = (current.astimezone(ZoneInfo("America/New_York")).date() - timedelta(days=1)).isoformat()
        patch.setattr(research, "_latest_saved_checkpoint", lambda _path: {
            "recorded_at_utc": (current - timedelta(hours=2)).isoformat(),
            "signal_session": signal,
            "candidates": [{
                "symbol": "AAA", "name": "AAA Corporation Common Stock",
                "adjusted_close": 20.0, "last_session": signal,
            }],
        })
        response = make_app().post("/api/research/budget-plan", json={
            "budget_usd": "100.00", "style": "balanced",
            "allow_experimental_stocks": True,
        })
        assert response.status_code == 200
        data = response.json()
        assert data["source_kind"] == "frozen_checkpoint"
        assert [row["amount_usd"] for row in data["allocation"]] == ["65.00", "10.00", "25.00"]
    finally:
        patch.undo()


def test_latest_pinned_shortlist_is_verified_before_display(tmp_path) -> None:
    signal = date(2026, 11, 13)
    finished = datetime(2026, 11, 14, 22, tzinfo=UTC)
    body = build_forward_record(
        started_at=finished - timedelta(minutes=1), finished_at=finished,
        latest_completed_session=signal, latest_scan_session=signal,
        directory_size=3, considered=2, processed=2, qualified=1,
        symbol_digest=universe_digest(["AAA", "BBB"]),
        candidates=[{"symbol": "AAA", "name": "AAA Corporation Common Stock",
                     "last_session": signal.isoformat(), "research_score": 1.5,
                     "adjusted_close": 25.0}],
        horizon=20,
    )
    path = tmp_path / "initial.json"
    digest = write_forward_record(path, body)
    register(tmp_path, path, checksum=digest)
    saved = research._latest_saved_checkpoint(tmp_path)
    assert saved is not None
    assert saved["signal_session"] == "2026-11-13"
    assert saved["candidates"][0]["symbol"] == "AAA"
    path.write_text(path.read_text().replace("AAA Corporation", "Fake Corporation"))
    with pytest.raises(research.JournalError):
        research._latest_saved_checkpoint(tmp_path)
