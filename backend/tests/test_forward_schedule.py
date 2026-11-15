"""Opt-in local scheduler never bypasses prospective research safeguards."""

import json
import os
import plistlib
from datetime import UTC, date, datetime
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest

from app.analysis import forward_schedule as schedule
from app.analysis.forward_journal import JournalError

NY = ZoneInfo("America/New_York")


def _at(day: int = 15, hour: int = 8, minute: int = 15) -> datetime:
    return datetime(2026, 11, day, hour, minute, tzinfo=NY)


def test_new_york_window_independent_of_utc_and_dst():
    assert schedule.in_ny_run_window(_at().astimezone(UTC))
    assert schedule.in_ny_run_window(datetime(2026, 6, 16, 8, 15, tzinfo=NY))
    assert not schedule.in_ny_run_window(_at(hour=7))
    assert not schedule.in_ny_run_window(_at(hour=9))
    assert not schedule.in_ny_run_window(_at(hour=23))


def test_naive_timestamp_is_rejected():
    with pytest.raises(schedule.ScheduleError, match="time zone"):
        schedule.in_ny_run_window(datetime(2026, 11, 15, 8, 15))


def test_outside_window_makes_zero_provider_calls_or_log_files(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "capture", lambda *_a, **_k: pytest.fail("provider called"))
    state, item = schedule.scheduled_capture(tmp_path, now=_at(hour=7))
    assert state == "outside_window"
    assert item is None
    assert not (tmp_path / "operations").exists()


def test_in_window_passes_same_utc_now_to_journal_and_records_success(tmp_path, monkeypatch):
    fake = SimpleNamespace(
        checkpoint=SimpleNamespace(signal_session=date(2026, 11, 13)),
        expected_sha256="a" * 64,
    )
    calls = []

    def capture(_root, *, horizon, now):
        calls.append((horizon, now))
        return "captured", fake

    monkeypatch.setattr(schedule, "capture", capture)
    state, item = schedule.scheduled_capture(tmp_path, horizon=20, now=_at())
    assert state == "captured" and item is fake
    assert calls == [(20, _at().astimezone(UTC))]
    attempts = schedule.read_attempts(tmp_path)
    assert attempts[0]["state"] == "captured"
    assert attempts[0]["checkpoint_sha256"] == "a" * 64
    assert (schedule.log_path(tmp_path).stat().st_mode & 0o777) == 0o600
    assert ((tmp_path / "operations").stat().st_mode & 0o777) == 0o700


def test_duplicate_state_is_recorded_without_extra_checkpoint(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "capture", lambda *_a, **_k: ("already_registered", None))
    state, item = schedule.scheduled_capture(tmp_path, now=_at())
    assert state == "already_registered" and item is None
    assert schedule.read_attempts(tmp_path)[0]["checkpoint_sha256"] is None


def test_late_state_does_not_claim_recorded_evidence(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule, "capture", lambda *_a, **_k: ("skipped_late", None))
    state, _ = schedule.scheduled_capture(tmp_path, now=_at())
    assert state == "skipped_late"
    assert schedule.read_attempts(tmp_path)[0]["signal_session"] is None


def test_failure_is_logged_then_raised_and_can_retry(tmp_path, monkeypatch):
    calls = [0]

    def flaky(*_args, **_kwargs):
        calls[0] += 1
        if calls[0] == 1:
            raise JournalError("provider unavailable")
        return "already_registered", None

    monkeypatch.setattr(schedule, "capture", flaky)
    with pytest.raises(JournalError, match="provider unavailable"):
        schedule.scheduled_capture(tmp_path, now=_at())
    assert schedule.scheduled_capture(tmp_path, now=_at())[0] == "already_registered"
    assert [row["state"] for row in schedule.read_attempts(tmp_path)] == [
        "failed", "already_registered",
    ]
    assert schedule.read_attempts(tmp_path)[0]["error_type"] == "JournalError"


@pytest.mark.parametrize("horizon", [0, -1, 253, True, 1.2])
def test_invalid_horizon_is_blocked_before_provider(tmp_path, monkeypatch, horizon):
    monkeypatch.setattr(schedule, "capture", lambda *_a, **_k: pytest.fail("provider called"))
    with pytest.raises(schedule.ScheduleError, match="Horizon"):
        schedule.scheduled_capture(tmp_path, horizon=horizon, now=_at())


def test_agent_config_runs_hourly_with_ny_gate_and_no_trades(tmp_path):
    backend = tmp_path / "backend"
    (backend / "app" / "analysis").mkdir(parents=True)
    (backend / "app" / "analysis" / "forward_journal_cli.py").write_text("# present")
    interpreter = tmp_path / "venv" / "bin" / "python"
    interpreter.parent.mkdir(parents=True)
    interpreter.write_text("# executable path exists")
    root = tmp_path / "research"
    root.mkdir()
    config = schedule.make_launch_agent(root=root, backend=backend, interpreter=interpreter)
    assert config["Label"] == schedule.AGENT_LABEL
    assert config["StartCalendarInterval"] == {"Minute": 15}
    assert config["RunAtLoad"] is False
    assert config["KeepAlive"] is False
    assert config["Umask"] == 0o077
    assert config["WorkingDirectory"] == str(backend)
    assert config["ProgramArguments"][:4] == [
        str(interpreter), "-m", "app.analysis.forward_schedule_cli", "run-once",
    ]
    assert str(root) in config["ProgramArguments"]
    assert all("SECRET" not in str(value) for value in config.values())
    assert (root / "operations").is_dir()


def test_agent_requires_existing_research_directory(tmp_path):
    with pytest.raises(schedule.ScheduleError, match="must already exist"):
        schedule.make_launch_agent(
            root=tmp_path / "missing", backend=tmp_path, interpreter=Path(os.__file__),
        )


def test_agent_requires_real_backend_and_interpreter(tmp_path):
    root = tmp_path / "research"
    root.mkdir()
    with pytest.raises(schedule.ScheduleError, match="existing forward journal"):
        schedule.make_launch_agent(root=root, backend=tmp_path, interpreter=Path(os.__file__))


def test_plist_is_non_overwriting_and_private(tmp_path):
    agents = tmp_path / "LaunchAgents"
    target = agents / schedule.PLIST_FILENAME
    schedule.save_launch_agent(target, {"Label": schedule.AGENT_LABEL})
    assert plistlib.loads(target.read_bytes())["Label"] == schedule.AGENT_LABEL
    assert (target.stat().st_mode & 0o777) == 0o600
    with pytest.raises(schedule.ScheduleError, match="already exists"):
        schedule.save_launch_agent(target, {"Label": "changed"})
    assert plistlib.loads(target.read_bytes())["Label"] == schedule.AGENT_LABEL


def test_plist_refuses_unexpected_filename(tmp_path):
    with pytest.raises(schedule.ScheduleError, match="unexpected"):
        schedule.save_launch_agent(tmp_path / "different.plist", {})


def test_log_reports_latest_attempts_without_network(tmp_path):
    for i in range(4):
        schedule._append_attempt(tmp_path, {
            "schema_version": schedule.LOG_SCHEMA,
            "attempted_at_utc": f"2026-11-14T0{i}:00:00+00:00",
            "horizon": 20,
            "state": "skipped_late",
        })
    assert len(schedule.read_attempts(tmp_path, limit=2)) == 2
    assert schedule.read_attempts(tmp_path, limit=2)[0]["attempted_at_utc"].startswith(
        "2026-11-14T02"
    )


def test_log_missing_is_empty(tmp_path):
    assert schedule.read_attempts(tmp_path) == []


def test_log_rejects_invalid_json(tmp_path):
    directory = tmp_path / "operations"
    directory.mkdir()
    (directory / "scheduler_attempts.jsonl").write_text("not-json\n")
    with pytest.raises(schedule.ScheduleError, match="Cannot read"):
        schedule.read_attempts(tmp_path)


def test_log_rejects_invalid_schema(tmp_path):
    directory = tmp_path / "operations"
    directory.mkdir()
    (directory / "scheduler_attempts.jsonl").write_text(json.dumps({"state": "captured"}))
    with pytest.raises(schedule.ScheduleError, match="Malformed"):
        schedule.read_attempts(tmp_path)


def test_log_rejects_symlink(tmp_path):
    directory = tmp_path / "operations"
    directory.mkdir()
    target = tmp_path / "outside.log"
    target.write_text("data")
    (directory / "scheduler_attempts.jsonl").symlink_to(target)
    with pytest.raises(schedule.ScheduleError, match="regular file"):
        schedule.read_attempts(tmp_path)


def test_limit_validation(tmp_path):
    with pytest.raises(schedule.ScheduleError, match="Limit"):
        schedule.read_attempts(tmp_path, limit=0)


def test_launch_agent_preserves_virtualenv_python_symlink(tmp_path):
    backend = tmp_path / "backend"
    (backend / "app" / "analysis").mkdir(parents=True)
    (backend / "app" / "analysis" / "forward_journal_cli.py").write_text("# present")
    system_python = tmp_path / "framework" / "python3.14"
    system_python.parent.mkdir()
    system_python.write_text("# fake system executable")
    virtual_python = tmp_path / ".venv" / "bin" / "python"
    virtual_python.parent.mkdir(parents=True)
    virtual_python.symlink_to(system_python)
    root = tmp_path / "research"
    root.mkdir()
    config = schedule.make_launch_agent(
        root=root, backend=backend, interpreter=virtual_python,
    )
    assert config["ProgramArguments"][0] == str(virtual_python)
    assert config["ProgramArguments"][0] != str(system_python)


def test_python_interpreter_uses_active_venv_path(tmp_path, monkeypatch):
    venv = tmp_path / ".venv"
    venv_python = venv / "bin" / "python"
    venv_python.parent.mkdir(parents=True)
    system_python = tmp_path / "framework" / "python3.14"
    system_python.parent.mkdir()
    system_python.write_text("# fake base python")
    venv_python.symlink_to(system_python)
    monkeypatch.setattr(schedule.sys, "prefix", str(venv))
    monkeypatch.setattr(schedule.sys, "base_prefix", str(tmp_path / "framework"))
    assert schedule.python_interpreter() == venv_python


def test_python_interpreter_refuses_global_python(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule.sys, "prefix", str(tmp_path))
    monkeypatch.setattr(schedule.sys, "base_prefix", str(tmp_path))
    with pytest.raises(schedule.ScheduleError, match="virtual environment"):
        schedule.python_interpreter()


def test_python_interpreter_refuses_missing_venv_binary(tmp_path, monkeypatch):
    monkeypatch.setattr(schedule.sys, "prefix", str(tmp_path / ".venv"))
    monkeypatch.setattr(schedule.sys, "base_prefix", str(tmp_path / "global"))
    with pytest.raises(schedule.ScheduleError, match="executable is missing"):
        schedule.python_interpreter()
