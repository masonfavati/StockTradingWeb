"""Daily forward checkpoints must be pinned, deduplicated, and never backdated."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis import forward_journal as journal
from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record

SIGNAL = date(2026, 11, 13)
NOW = datetime(2026, 11, 14, 22, tzinfo=UTC)
ORIGINAL = "a" * 64


def _body(*, signal: date = SIGNAL, horizon: int = 20, symbol: str = "AAPL"):
    return build_forward_record(
        started_at=NOW - timedelta(minutes=2),
        finished_at=NOW,
        latest_completed_session=signal,
        latest_scan_session=signal,
        directory_size=100,
        considered=80,
        processed=80,
        qualified=1,
        symbol_digest=universe_digest(["AAPL", "MSFT"]),
        candidates=[{
            "symbol": symbol,
            "last_session": signal.isoformat(),
            "research_score": 0.61,
        }],
        horizon=horizon,
    )


def _record(tmp_path: Path, *, name: str = "legacy.json", **changes):
    path = tmp_path / name
    digest = write_forward_record(path, _body(**changes))
    return path, digest


def _calendar(*_args, **_kwargs):
    return {SIGNAL, date(2026, 11, 16), date(2026, 11, 17)}


def test_register_original_checkpoint_and_preserve_source(tmp_path):
    source, digest = _record(tmp_path)
    original = source.read_bytes()
    entry, created = journal.register(tmp_path, source, checksum=digest)
    assert created
    assert entry.expected_sha256 == digest
    assert entry.checkpoint.shortlist == ("AAPL",)
    assert source.read_bytes() == original
    assert len(journal.entries(tmp_path)) == 1
    assert entry.pin_path.stat().st_mode & 0o777 == 0o600


def test_register_is_idempotent_not_a_rewritten_pin(tmp_path):
    source, digest = _record(tmp_path)
    entry, _ = journal.register(tmp_path, source, checksum=digest)
    before = entry.pin_path.read_bytes()
    later, created = journal.register(tmp_path, source, checksum=digest)
    assert not created
    assert later.pin_path == entry.pin_path
    assert later.pin_path.read_bytes() == before


def test_same_date_rule_horizon_with_conflicting_checkpoint_is_blocked(tmp_path):
    first, checksum = _record(tmp_path, name="first.json")
    journal.register(tmp_path, first, checksum=checksum)
    second, other = _record(tmp_path, name="second.json", symbol="MSFT")
    with pytest.raises(journal.JournalError, match="Conflicting"):
        journal.register(tmp_path, second, checksum=other)
    assert len(journal.entries(tmp_path)) == 1


def test_invalid_original_sha256_is_not_accepted(tmp_path):
    source, _ = _record(tmp_path)
    with pytest.raises(journal.JournalError, match="mismatch"):
        journal.register(tmp_path, source, checksum=ORIGINAL)
    assert journal.entries(tmp_path) == []


def test_corrupt_checkpoint_invalidates_registered_journal(tmp_path):
    source, digest = _record(tmp_path)
    journal.register(tmp_path, source, checksum=digest)
    source.write_text(source.read_text().replace('"AAPL"', '"TSLA"', 1))
    with pytest.raises(journal.JournalError, match="Pinned checkpoint failed"):
        journal.entries(tmp_path)


def test_corrupt_journal_pin_detected(tmp_path):
    source, digest = _record(tmp_path)
    entry, _ = journal.register(tmp_path, source, checksum=digest)
    text = entry.pin_path.read_text()
    entry.pin_path.write_text(text.replace('"horizon": 20', '"horizon": 19'))
    with pytest.raises(journal.JournalError, match="altered"):
        journal.entries(tmp_path)


def test_duplicate_json_keys_detected_even_with_correct_old_hash(tmp_path):
    source, digest = _record(tmp_path)
    entry, _ = journal.register(tmp_path, source, checksum=digest)
    text = entry.pin_path.read_text()
    entry.pin_path.write_text(text.replace('"horizon":', '"horizon": 20, "horizon":', 1))
    with pytest.raises(journal.JournalError, match="Duplicate JSON key"):
        journal.entries(tmp_path)


def test_missing_or_moved_checkpoint_fails_closed(tmp_path):
    source, digest = _record(tmp_path)
    journal.register(tmp_path, source, checksum=digest)
    source.unlink()
    with pytest.raises(journal.JournalError, match="Pinned checkpoint failed"):
        journal.entries(tmp_path)


def test_capture_skips_previously_registered_signal_before_full_scan(tmp_path, monkeypatch):
    source, digest = _record(tmp_path)
    journal.register(tmp_path, source, checksum=digest)
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)

    def no_scan(*_args, **_kwargs):
        raise AssertionError("Should not request 13,498 symbols again")

    monkeypatch.setattr(journal.subprocess, "run", no_scan)
    state, entry = journal.capture(tmp_path, now=NOW, settings=object())
    assert state == "already_registered"
    assert entry is not None and entry.expected_sha256 == digest


def test_capture_refuses_entry_day_at_or_after_nine_ny(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)
    monkeypatch.setattr(journal.subprocess, "run", lambda *_a, **_k: pytest.fail("scan ran"))
    state, entry = journal.capture(
        tmp_path, now=datetime(2026, 11, 16, 14, tzinfo=UTC), settings=object(),
    )
    assert state == "skipped_late"
    assert entry is None
    assert journal.entries(tmp_path) == []


def test_capture_one_scan_then_register_and_skip_second(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)
    calls = []

    def scan(command, **_kwargs):
        calls.append(command)
        target = Path(command[command.index("--out") + 1])
        write_forward_record(target, _body())
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(journal.subprocess, "run", scan)
    state, entry = journal.capture(tmp_path, now=NOW, settings=object())
    assert state == "captured" and entry is not None
    assert entry.record_path.name == "forward_2026-11-13_h020.json"
    assert entry.checkpoint.signal_session == SIGNAL
    again, _ = journal.capture(tmp_path, now=NOW, settings=object())
    assert again == "already_registered"
    assert len(calls) == 1
    assert len(journal.entries(tmp_path)) == 1


def test_entry_date_preopen_capture_can_register(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)
    started = datetime(2026, 11, 16, 13, 15, tzinfo=UTC)

    def scan(command, **_kwargs):
        target = Path(command[command.index("--out") + 1])
        body = _body()
        body["recorded_at_utc"] = "2026-11-16T13:30:00+00:00"
        write_forward_record(target, body)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(journal.subprocess, "run", scan)
    state, entry = journal.capture(tmp_path, now=started, settings=object())
    assert state == "captured"
    assert entry is not None
    assert entry.checkpoint.signal_session == SIGNAL


def test_failed_full_scan_creates_no_pin(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)
    monkeypatch.setattr(
        journal.subprocess, "run", lambda *_args, **_kwargs: SimpleNamespace(returncode=1),
    )
    with pytest.raises(journal.JournalError, match="full market scan failed"):
        journal.capture(tmp_path, now=NOW, settings=object())
    assert journal.entries(tmp_path) == []


def test_unregistered_file_not_overwritten_on_retry(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)
    checkpoint_dir = tmp_path / "checkpoints"
    checkpoint_dir.mkdir()
    target = checkpoint_dir / "forward_2026-11-13_h020.json"
    target.write_text("ORPHANED EVIDENCE")
    monkeypatch.setattr(journal.subprocess, "run", lambda *_a, **_k: pytest.fail("rescan"))
    with pytest.raises(journal.JournalError, match="unregistered checkpoint"):
        journal.capture(tmp_path, now=NOW, settings=object())
    assert target.read_text() == "ORPHANED EVIDENCE"


def test_capture_rejects_other_signal_even_if_scan_says_success(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)

    def wrong_signal(command, **_kwargs):
        target = Path(command[command.index("--out") + 1])
        # This mismatched candidate session would be caught after hash validation.
        write_forward_record(target, _body(signal=date(2026, 11, 12)))
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(journal.subprocess, "run", wrong_signal)
    with pytest.raises(journal.JournalError, match="does not match"):
        journal.capture(tmp_path, now=NOW, settings=object())
    assert journal.entries(tmp_path) == []


def test_status_empty_never_fetches_market_calendar(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", lambda **_k: pytest.fail("calendar"))
    assert journal.status_rows(tmp_path) == []


def test_status_pending_with_no_future_sessions(tmp_path, monkeypatch):
    source, digest = _record(tmp_path)
    journal.register(tmp_path, source, checksum=digest)
    monkeypatch.setattr(journal, "get_market_calendar", lambda **_k: {SIGNAL})
    rows = journal.status_rows(tmp_path, now=NOW, settings=object())
    assert len(rows) == 1
    assert rows[0].state == "PENDING"
    assert rows[0].observed == 0
    assert rows[0].required == 21


def test_status_ready_only_after_all_future_sessions(tmp_path, monkeypatch):
    source, digest = _record(tmp_path)
    journal.register(tmp_path, source, checksum=digest)
    future = []
    day = SIGNAL + timedelta(days=1)
    while len(future) < 21:
        if day.weekday() < 5:
            future.append(day)
        day += timedelta(days=1)
    monkeypatch.setattr(journal, "get_market_calendar", lambda **_k: {SIGNAL, *future})
    # Use a completed cutoff beyond the final session in fake calendar.
    monkeypatch.setattr(
        journal, "completed_session_cutoff",
        lambda **_k: datetime.combine(future[-1], datetime.max.time(), tzinfo=UTC),
    )
    rows = journal.status_rows(tmp_path, now=NOW, settings=object())
    assert rows[0].state == "READY"
    assert rows[0].observed == 21


def test_unexpected_non_json_journal_item_blocks_report(tmp_path):
    (tmp_path / "journal").mkdir()
    (tmp_path / "journal" / "notes.txt").write_text("hidden")
    with pytest.raises(journal.JournalError, match="Unexpected"):
        journal.entries(tmp_path)


def test_pin_is_parseable_json_with_source_binding(tmp_path):
    source, digest = _record(tmp_path)
    entry, _ = journal.register(tmp_path, source, checksum=digest)
    pin = json.loads(entry.pin_path.read_text())
    assert pin["checkpoint_sha256"] == digest
    assert pin["checkpoint_path"] == str(source.resolve())
    assert pin["research_rule"] == entry.checkpoint.research_rule


def test_capture_rejects_invalid_horizon_before_any_provider_request(tmp_path):
    with pytest.raises(journal.JournalError, match="Horizon"):
        journal.capture(tmp_path, horizon=0)


def test_completed_scan_reaching_nine_am_entry_day_does_not_register(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", _calendar)

    def after_midnight(command, **_kwargs):
        target = Path(command[command.index("--out") + 1])
        body = _body()
        body["recorded_at_utc"] = "2026-11-16T14:00:00+00:00"
        write_forward_record(target, body)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(journal.subprocess, "run", after_midnight)
    with pytest.raises(journal.JournalError, match="does not match"):
        journal.capture(tmp_path, now=NOW, settings=object())
    assert journal.entries(tmp_path) == []
    assert len(list((tmp_path / "checkpoints").glob("*.json"))) == 1


def test_capture_must_verify_future_exchange_session(tmp_path, monkeypatch):
    monkeypatch.setattr(journal, "get_market_calendar", lambda **_k: {SIGNAL})
    monkeypatch.setattr(journal.subprocess, "run", lambda *_a, **_k: pytest.fail("scan"))
    with pytest.raises(journal.JournalError, match="Next exchange"):
        journal.capture(tmp_path, now=NOW, settings=object())


def test_explicit_missing_original_checksum_is_rejected(tmp_path):
    source, _ = _record(tmp_path)
    with pytest.raises(journal.JournalError, match="64-character"):
        journal.register(tmp_path, source, checksum="")
