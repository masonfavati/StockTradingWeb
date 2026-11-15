"""Opt-in macOS forward-research scheduling, never automatic trading.

Launchd wakes this module hourly. Only the 08:00–08:59 New York hour
is eligible; all other invocations exit without contacting Alpaca.
A sleeping/offline computer may miss an event. We never backdate one.
"""

import fcntl
import json
import os
import plistlib
import sys
from collections.abc import Mapping
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.analysis.forward_journal import JournalEntry, JournalError, capture
from app.market_data.history_audit import CalendarError

AGENT_LABEL = "com.stocktradingweb.forward-research"
PLIST_FILENAME = f"{AGENT_LABEL}.plist"
NY = ZoneInfo("America/New_York")
SCHEDULE_HOUR_NY = 8
LAUNCHD_MINUTE = 15
LOG_SCHEMA = "forward-research-scheduler-attempt-v1"


class ScheduleError(ValueError):
    """Unable to prepare an opt-in scheduler configuration or history."""


def _valid_now(now: datetime) -> datetime:
    if now.tzinfo is None or now.utcoffset() is None:
        raise ScheduleError("Current time must include a time zone")
    return now.astimezone(UTC)


def in_ny_run_window(now: datetime) -> bool:
    """Use the *New York* clock, independent of the computer's time zone."""
    return _valid_now(now).astimezone(NY).hour == SCHEDULE_HOUR_NY


def _operations_dir(root: Path) -> Path:
    if not root.is_dir():
        raise ScheduleError("Research directory must already exist")
    directory = root / "operations"
    if directory.is_symlink():
        raise ScheduleError("Operations directory cannot be a symbolic link")
    directory.mkdir(mode=0o700, exist_ok=True)
    return directory


def log_path(root: Path) -> Path:
    return root / "operations" / "scheduler_attempts.jsonl"


def _append_attempt(root: Path, payload: Mapping[str, Any]) -> None:
    """Serialize process-local attempts; operational log is NOT certified proof."""
    _operations_dir(root)
    path = log_path(root)
    encoded = (json.dumps(dict(payload), sort_keys=True, allow_nan=False) + "\n").encode()
    descriptor = os.open(path, os.O_CREAT | os.O_APPEND | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, "ab") as stream:
        fcntl.flock(stream.fileno(), fcntl.LOCK_EX)
        try:
            stream.write(encoded)
            stream.flush()
            os.fsync(stream.fileno())
        finally:
            fcntl.flock(stream.fileno(), fcntl.LOCK_UN)


def scheduled_capture(
    root: Path, *, horizon: int = 20, now: datetime | None = None,
) -> tuple[str, JournalEntry | None]:
    """Run only in the strict NY window; existing journal owns scan safety.

    A failed invocation gets an operational record and propagates an error.
    No automatic retries, retroactive scans, or fictitious checkpoints.
    """
    current = _valid_now(now or datetime.now(UTC))
    if type(horizon) is not int or not 1 <= horizon <= 252:
        raise ScheduleError("Horizon must be 1–252 trading sessions")
    if not in_ny_run_window(current):
        return "outside_window", None
    try:
        state, item = capture(root, horizon=horizon, now=current)
    except (JournalError, CalendarError, OSError, ValueError) as exc:
        _append_attempt(root, {
            "schema_version": LOG_SCHEMA,
            "attempted_at_utc": current.isoformat(),
            "horizon": horizon,
            "state": "failed",
            "error_type": type(exc).__name__,
        })
        raise
    _append_attempt(root, {
        "schema_version": LOG_SCHEMA,
        "attempted_at_utc": current.isoformat(),
        "horizon": horizon,
        "state": state,
        "signal_session": item.checkpoint.signal_session.isoformat() if item else None,
        "checkpoint_sha256": item.expected_sha256 if item else None,
    })
    return state, item


def make_launch_agent(
    *, root: Path, backend: Path, interpreter: Path,
) -> dict[str, Any]:
    """Return a macOS LaunchAgent; no install/load side effects."""
    root = root.expanduser().resolve()
    backend = backend.expanduser().resolve()
    # Keep the virtualenv launcher path: resolving a symlink in .venv/bin
    # points to system Python and loses the project's installed packages.
    interpreter = interpreter.expanduser().absolute()
    if not root.is_dir():
        raise ScheduleError("Research directory must already exist")
    if not (backend / "app" / "analysis" / "forward_journal_cli.py").is_file():
        raise ScheduleError("Backend does not contain the existing forward journal")
    if not interpreter.is_file():
        raise ScheduleError("Python interpreter path is unavailable")
    operations = _operations_dir(root)
    return {
        "Label": AGENT_LABEL,
        "ProgramArguments": [
            str(interpreter), "-m", "app.analysis.forward_schedule_cli", "run-once",
            "--dir", str(root), "--horizon", "20",
        ],
        "WorkingDirectory": str(backend),
        # An hourly schedule plus a New York hour gate is DST-safe even if
        # the user's Mac has another system time zone.
        "StartCalendarInterval": {"Minute": LAUNCHD_MINUTE},
        "RunAtLoad": False,
        "KeepAlive": False,
        "StandardOutPath": str(operations / "launchd.stdout.log"),
        "StandardErrorPath": str(operations / "launchd.stderr.log"),
        "EnvironmentVariables": {"PYTHONUNBUFFERED": "1"},
        "Umask": 0o077,
    }


def save_launch_agent(path: Path, config: Mapping[str, Any]) -> None:
    """Create an opt-in plist without replacing an existing installation."""
    path = path.expanduser()
    if path.name != PLIST_FILENAME:
        raise ScheduleError("Refusing an unexpected LaunchAgent filename")
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    data = plistlib.dumps(dict(config), sort_keys=True)
    try:
        descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    except FileExistsError as exc:
        raise ScheduleError("Agent file already exists; no replacement performed") from exc
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, KeyboardInterrupt):
        path.unlink(missing_ok=True)
        raise


def read_attempts(root: Path, *, limit: int = 10) -> list[dict[str, Any]]:
    """Show recent operational attempts; does not contact Alpaca."""
    if type(limit) is not int or not 1 <= limit <= 100:
        raise ScheduleError("Limit must be 1–100")
    path = log_path(root)
    if not path.exists():
        return []
    if path.is_symlink() or not path.is_file():
        raise ScheduleError("Attempt log is not a regular file")
    if path.stat().st_size > 20_000_000:
        raise ScheduleError("Attempt log exceeds 20 MB; archive it before inspection")
    rows: list[dict[str, Any]] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
        for line in lines[-limit:]:
            value = json.loads(line)
            if (
                not isinstance(value, dict)
                or value.get("schema_version") != LOG_SCHEMA
                or value.get("state") not in {
                    "captured", "skipped_late", "already_registered", "failed"
                }
                or not isinstance(value.get("attempted_at_utc"), str)
            ):
                raise ScheduleError("Malformed scheduler attempt record")
            rows.append(value)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ScheduleError("Cannot read scheduler attempt log") from exc
    return rows


def default_agent_path() -> Path:
    return Path.home() / "Library" / "LaunchAgents" / PLIST_FILENAME


def backend_dir() -> Path:
    return Path(__file__).resolve().parents[2]


def python_interpreter() -> Path:
    """Use the active project venv, not its symlink target in system Python."""
    if sys.prefix == sys.base_prefix:
        raise ScheduleError(
            "Scheduler setup requires the project virtual environment; "
            "invoke with 'uv run python -m app.analysis.forward_schedule_cli plan ...'"
        )
    interpreter = Path(sys.prefix).expanduser().absolute() / "bin" / "python"
    if not interpreter.is_file():
        raise ScheduleError("Project virtual environment Python executable is missing")
    return interpreter
