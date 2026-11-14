from datetime import UTC, datetime, timedelta

from pytest import MonkeyPatch

import app.api.scanner as scanner_module
from app.api.scanner import ScanManager


def test_scan_manager_is_single_run_and_reports_progress() -> None:
    job = ScanManager()
    now = datetime(2026, 11, 14, tzinfo=UTC)
    assert job.snapshot().state == "idle"
    assert job.begin(now=now)
    assert not job.begin(now=now + timedelta(seconds=1))
    job.progress(50, 100)
    state = job.snapshot()
    assert state.state == "running"
    assert (state.processed, state.considered) == (50, 100)
    assert state.candidates == []


def test_failed_scan_never_publishes_partial_rankings() -> None:
    patch = MonkeyPatch()
    try:
        job = ScanManager()
        assert job.begin(now=datetime.now(UTC))

        def fail(*_args: object, **_kwargs: object) -> None:
            raise RuntimeError("fake upstream error")

        patch.setattr(scanner_module, "scan_market", fail)
        job.execute()
        state = job.snapshot()
        assert state.state == "failed"
        assert state.candidates == []
        assert "RuntimeError" in state.message
        assert "fake upstream error" not in state.message
    finally:
        patch.undo()
