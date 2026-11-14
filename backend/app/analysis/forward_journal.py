"""Pin independent prospective scans and inventory their maturity without outcomes.

This is a local integrity journal, NOT a cryptographic timestamp authority.
The journal never edits source checkpoints, evaluates returns, or trades.
"""

import fcntl
import hashlib
import json
import os
import re
import subprocess
import sys
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from app.analysis.forward_evaluation import (
    ForwardEvaluationError,
    FrozenCheckpoint,
    evaluation_window,
    load_checkpoint,
)
from app.analysis.forward_record import SCANNER_RULE_ID, write_forward_record
from app.core.config import Settings
from app.market_data.history_audit import get_market_calendar
from app.market_data.history_import import completed_session_cutoff

NY = ZoneInfo("America/New_York")
PIN_SCHEMA = "forward-research-journal-pin-v1"
_SHA256 = re.compile(r"[0-9a-f]{64}\Z")


class JournalError(ValueError):
    """A journal operation was unsafe or would create ambiguous evidence."""


@dataclass(frozen=True)
class JournalEntry:
    """A frozen source and an independently specified digest stored in the journal."""

    record_path: Path
    expected_sha256: str
    checkpoint: FrozenCheckpoint
    pin_path: Path

    @property
    def key(self) -> tuple[date, int, str]:
        return (
            self.checkpoint.signal_session,
            self.checkpoint.horizon,
            self.checkpoint.research_rule,
        )


def _pin_filename(signal: date, horizon: int, rule: str) -> str:
    rule_hash = hashlib.sha256(rule.encode("utf-8")).hexdigest()[:20]
    return f"{signal.isoformat()}_h{horizon:03d}_{rule_hash}.json"


def _unique_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    found: dict[str, Any] = {}
    for key, value in pairs:
        if key in found:
            raise JournalError(f"Duplicate JSON key in journal: {key}")
        found[key] = value
    return found


def _nonfinite(value: str) -> None:
    raise JournalError(f"Nonfinite JSON value in journal: {value}")


def _read_json(path: Path, *, max_bytes: int = 64_000) -> dict[str, Any]:
    if path.stat().st_size > max_bytes:
        raise JournalError(f"Journal pin is too large: {path.name}")
    try:
        data = json.loads(
            path.read_text(encoding="utf-8"),
            object_pairs_hook=_unique_pairs,
            parse_constant=_nonfinite,
        )
    except JournalError:
        raise
    except (ValueError, UnicodeError) as exc:
        raise JournalError(f"Invalid journal pin: {path.name}") from exc
    if not isinstance(data, dict):
        raise JournalError(f"Journal pin is not an object: {path.name}")
    return data


def _checked_pin(path: Path) -> JournalEntry:
    body = _read_json(path)
    digest = body.get("content_sha256")
    if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
        raise JournalError(f"Journal pin lacks its checksum: {path.name}")
    raw = {key: value for key, value in body.items() if key != "content_sha256"}
    actual = hashlib.sha256(
        json.dumps(raw, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()
    ).hexdigest()
    if actual != digest:
        raise JournalError(f"Journal pin was altered: {path.name}")
    if raw.get("schema_version") != PIN_SCHEMA or set(raw) != {
        "schema_version", "checkpoint_path", "checkpoint_sha256",
        "signal_session", "horizon", "research_rule",
    }:
        raise JournalError(f"Unsupported journal pin format: {path.name}")
    source = raw["checkpoint_path"]
    expected = raw["checkpoint_sha256"]
    if not isinstance(source, str) or not source or not Path(source).is_absolute():
        raise JournalError(f"Journal checkpoint path is invalid: {path.name}")
    if not isinstance(expected, str) or _SHA256.fullmatch(expected) is None:
        raise JournalError(f"Journal checkpoint digest is invalid: {path.name}")
    try:
        checkpoint = load_checkpoint(Path(source), expected_checksum=expected)
    except (OSError, ForwardEvaluationError) as exc:
        raise JournalError(f"Pinned checkpoint failed verification: {path.name}: {exc}") from exc
    if (
        raw["signal_session"] != checkpoint.signal_session.isoformat()
        or type(raw["horizon"]) is not int
        or raw["horizon"] != checkpoint.horizon
        or raw["research_rule"] != checkpoint.research_rule
        or path.name != _pin_filename(
            checkpoint.signal_session, checkpoint.horizon, checkpoint.research_rule
        )
    ):
        raise JournalError(f"Journal identity does not match checkpoint: {path.name}")
    return JournalEntry(Path(source), expected, checkpoint, path)


def entries(root: Path) -> list[JournalEntry]:
    """Verify every registered source; corruption anywhere stops the report."""
    index = root / "journal"
    if not index.exists():
        return []
    if not index.is_dir():
        raise JournalError("Journal index path is not a directory")
    result: list[JournalEntry] = []
    keys: set[tuple[date, int, str]] = set()
    for path in sorted(index.iterdir()):
        if path.name.startswith("."):
            continue
        if not path.is_file() or path.suffix != ".json":
            raise JournalError(f"Unexpected journal index item: {path.name}")
        entry = _checked_pin(path)
        if entry.key in keys:
            raise JournalError("Duplicate prospective signal in research journal")
        keys.add(entry.key)
        result.append(entry)
    return sorted(result, key=lambda item: item.key)


@contextmanager
def journal_lock(root: Path) -> Iterator[None]:
    """Serialize register/capture on macOS/Linux (fcntl advisory file lock)."""
    root.mkdir(mode=0o700, parents=True, exist_ok=True)
    if not root.is_dir():
        raise JournalError("Research destination is not a directory")
    lock = root / ".forward-journal.lock"
    descriptor = os.open(lock, os.O_CREAT | os.O_RDWR, 0o600)
    with os.fdopen(descriptor, "a+b") as file:
        fcntl.flock(file.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(file.fileno(), fcntl.LOCK_UN)


def _register_locked(root: Path, record_path: Path, checksum: str) -> tuple[JournalEntry, bool]:
    """Register under a held lock; returns (entry, newly_created)."""
    if _SHA256.fullmatch(checksum) is None:
        raise JournalError("Provide the original 64-character lowercase SHA-256 checksum")
    try:
        source = record_path.resolve(strict=True)
        checkpoint = load_checkpoint(source, expected_checksum=checksum)
    except (OSError, ForwardEvaluationError) as exc:
        raise JournalError(f"Cannot verify source checkpoint: {exc}") from exc
    key = (checkpoint.signal_session, checkpoint.horizon, checkpoint.research_rule)
    existing = {item.key: item for item in entries(root)}
    if key in existing:
        prior = existing[key]
        if prior.expected_sha256 != checksum:
            raise JournalError("Conflicting checkpoint for the same signal/rule/horizon; NOT overwritten")
        return prior, False
    index = root / "journal"
    index.mkdir(mode=0o700, parents=True, exist_ok=True)
    path = index / _pin_filename(*key)
    pin_body = {
        "schema_version": PIN_SCHEMA,
        "checkpoint_path": str(source),
        "checkpoint_sha256": checksum,
        "signal_session": checkpoint.signal_session.isoformat(),
        "horizon": checkpoint.horizon,
        "research_rule": checkpoint.research_rule,
    }
    try:
        write_forward_record(path, pin_body)
    except FileExistsError as exc:
        raise JournalError("Journal entry already exists, refusing to replace") from exc
    return JournalEntry(source, checksum, checkpoint, path), True


def register(root: Path, record_path: Path, *, checksum: str) -> tuple[JournalEntry, bool]:
    """Import an older immutable checkpoint using its original printed digest."""
    with journal_lock(root):
        return _register_locked(root, record_path, checksum)


def capture(
    root: Path,
    *,
    horizon: int = 20,
    now: datetime | None = None,
    settings: Settings | None = None,
) -> tuple[str, JournalEntry | None]:
    """Run the existing complete scanner once per (signal, horizon, rule).

    Preflight checks happen BEFORE the full market scan. A failed scan does
    not create a journal pin. A surviving orphan checkpoint must be manually
    inspected/registered; evidence is never silently deleted or replaced.
    """
    if type(horizon) is not int or not 1 <= horizon <= 252:
        raise JournalError("Horizon must be 1–252 exchange sessions")
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise JournalError("Current time must be timezone-aware")
    current = current.astimezone(UTC)
    with journal_lock(root):
        existing = {item.key: item for item in entries(root)}
        cutoff = completed_session_cutoff(now=current).astimezone(NY).date()
        calendar = get_market_calendar(
            start=cutoff - timedelta(days=14),
            end=cutoff + timedelta(days=14),
            settings=settings or Settings(),
        )
        past = sorted(day for day in calendar if day <= cutoff)
        if not past:
            raise JournalError("No verified completed exchange session")
        signal = past[-1]
        future = sorted(day for day in calendar if day > signal)
        if not future:
            raise JournalError("Next exchange session could not be verified")
        entry_session = future[0]
        # Current outcome evaluator conservatively requires a PRIOR calendar
        # date, not merely a clock time before the next session's open.
        if current.astimezone(NY).date() >= entry_session:
            return "skipped_late", None
        key = (signal, horizon, SCANNER_RULE_ID)
        if key in existing:
            return "already_registered", existing[key]
        directory = root / "checkpoints"
        directory.mkdir(mode=0o700, parents=True, exist_ok=True)
        target = directory / f"forward_{signal.isoformat()}_h{horizon:03d}.json"
        if target.exists():
            raise JournalError(
                f"An unregistered checkpoint already exists at {target}; "
                "inspect and register it, never overwrite it"
            )
        command = [
            sys.executable, "-m", "app.analysis.forward_cli",
            "--out", str(target), "--horizon", str(horizon),
        ]
        finished = subprocess.run(command, check=False)
        if finished.returncode:
            raise JournalError(
                "The full market scan failed; no journal pin was created. "
                "Inspect any checkpoint before retrying"
            )
        try:
            source = _read_json(target, max_bytes=1_000_000)
        except JournalError as exc:
            raise JournalError("Scan output could not be registered safely") from exc
        digest = source.get("content_sha256")
        if not isinstance(digest, str) or _SHA256.fullmatch(digest) is None:
            raise JournalError("Scanner output is missing its checksum")
        checkpoint = load_checkpoint(target, expected_checksum=digest)
        if (
            checkpoint.signal_session != signal
            or checkpoint.horizon != horizon
            or checkpoint.research_rule != SCANNER_RULE_ID
            or checkpoint.recorded_at_utc < current
            or checkpoint.recorded_at_utc.astimezone(NY).date() >= entry_session
        ):
            raise JournalError(
                "Scanner output does not match the preflight signal/rule/horizon; "
                "checkpoint retained but NOT registered"
            )
        entry, _ = _register_locked(root, target, digest)
        return "captured", entry


@dataclass(frozen=True)
class StatusRow:
    entry: JournalEntry
    state: str
    observed: int
    required: int


def status_rows(
    root: Path, *, now: datetime | None = None, settings: Settings | None = None,
) -> list[StatusRow]:
    """Check maturity with a shared independent calendar; never fetch prices."""
    available = entries(root)
    if not available:
        return []
    current = now or datetime.now(UTC)
    if current.tzinfo is None or current.utcoffset() is None:
        raise JournalError("Current time must be timezone-aware")
    cutoff = completed_session_cutoff(now=current).astimezone(NY).date()
    first = min(entry.checkpoint.signal_session for entry in available)
    if first > cutoff:
        raise JournalError("Registered checkpoint signal is after completed-data cutoff")
    calendar = get_market_calendar(start=first, end=cutoff, settings=settings or Settings())
    results: list[StatusRow] = []
    for entry in available:
        cp = entry.checkpoint
        try:
            window = evaluation_window(cp, sessions=calendar, completed_through=cutoff)
        except ForwardEvaluationError as exc:
            raise JournalError(f"Checkpoint is not safely evaluable: {entry.record_path}: {exc}") from exc
        results.append(StatusRow(
            entry=entry,
            state="READY" if window.is_mature else "PENDING",
            observed=window.observed_future_sessions,
            required=window.required_future_sessions,
        ))
    return results
