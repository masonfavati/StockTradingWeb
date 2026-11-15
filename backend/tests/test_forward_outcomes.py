"""Matured prospective records must be evaluated without rewriting history."""

import json
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace

import pytest

from app.analysis import forward_outcomes as outcome
from app.analysis.forward_journal import StatusRow, register
from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record

SIGNAL = date(2026, 11, 13)
NOW = datetime(2026, 11, 14, 22, tzinfo=UTC)


def _register(root: Path, name: str = "original.json", signal: date = SIGNAL):
    body = build_forward_record(
        started_at=NOW - timedelta(minutes=1),
        finished_at=NOW,
        latest_completed_session=signal,
        latest_scan_session=signal,
        directory_size=100,
        considered=99,
        processed=99,
        qualified=1,
        symbol_digest=universe_digest(["AAPL", "SPY"]),
        candidates=[{"symbol": "AAPL", "last_session": signal.isoformat(), "research_score": 0.5}],
        horizon=20,
    )
    record = root / name
    digest = write_forward_record(record, body)
    entry, _ = register(root, record, checksum=digest)
    return entry


def _row(entry, state="READY"):
    return StatusRow(entry, state, 21 if state == "READY" else 2, 21)


def _write_audit(root: Path, entry, *, status="complete", cost="10"):
    path = outcome.audit_path(root, entry)
    path.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    comparison = {
        "selected_equal_weight_net_return_pct": "3.0000",
        "benchmark_net_return_pct": "1.0000",
        "excess_vs_benchmark_percentage_points": "2.0000",
    } if status == "complete" else None
    body = {
        "schema_version": "forward-outcome-audit-v1",
        "source_checkpoint_sha256": entry.expected_sha256,
        "source_checkpoint_recorded_at_utc": entry.checkpoint.recorded_at_utc.isoformat(),
        "source_research_rule": entry.checkpoint.research_rule,
        "signal_session": entry.checkpoint.signal_session.isoformat(),
        "holding_sessions": entry.checkpoint.horizon,
        "selected_count": len(entry.checkpoint.shortlist),
        "assumed_cost_bps_each_side": cost,
        "benchmark_symbol": "SPY",
        "data_provider": "alpaca",
        "feed": "sip",
        "outcome_adjustment": "split",
        "entry_exit_price_type": "daily_open",
        "status": status,
        "selected_outcomes": [
            {"rank": rank, "symbol": symbol, "status": "complete" if status == "complete" else "missing_exit_open"}
            for rank, symbol in enumerate(entry.checkpoint.shortlist, start=1)
        ],
        "benchmark_outcome": {"symbol": "SPY", "status": "complete"},
        "complete_portfolio_comparison": comparison,
    }
    digest = write_forward_record(path, body)
    return path, digest


def test_empty_journal_is_empty(tmp_path, monkeypatch):
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [])
    assert outcome.outcome_status(tmp_path) == []


def test_pending_does_not_fetch_prices_or_create_files(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry, "PENDING")])
    monkeypatch.setattr(outcome.subprocess, "run", lambda *args, **kwargs: pytest.fail("Early price request"))
    result = outcome.evaluate_ready(tmp_path)
    assert not result.evaluated and not result.failed
    assert outcome.outcome_status(tmp_path)[0].state == "PENDING"
    assert not (tmp_path / "outcomes").exists()


def test_mature_without_audit_is_ready(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    assert outcome.outcome_status(tmp_path)[0].state == "READY"


def test_valid_complete_audit_and_returns(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    _, digest = _write_audit(tmp_path, entry)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    status = outcome.outcome_status(tmp_path)[0]
    assert status.state == "COMPLETE"
    assert status.audit_sha256 == digest
    assert status.excess_percentage_points == "2.0000"


def test_missing_outcomes_are_never_claimed_as_performance(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    _write_audit(tmp_path, entry, status="incomplete_outcomes")
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    status = outcome.outcome_status(tmp_path)[0]
    assert status.state == "INCOMPLETE"
    assert status.selected_return_pct is None
    assert status.excess_percentage_points is None


def test_outcome_tampering_detected(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    path, _ = _write_audit(tmp_path, entry)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    body = json.loads(path.read_text())
    body["status"] = "incomplete_outcomes"
    path.write_text(json.dumps(body))
    with pytest.raises(outcome.OutcomeJournalError, match="checksum mismatch"):
        outcome.outcome_status(tmp_path)


def test_inconsistent_checksum_cost_still_rejected(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    _write_audit(tmp_path, entry, cost="15")
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    with pytest.raises(outcome.OutcomeJournalError, match="inconsistent"):
        outcome.outcome_status(tmp_path)


def test_unrelated_checkpoint_rejected(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    path, _ = _write_audit(tmp_path, entry)
    body = json.loads(path.read_text())
    body["source_checkpoint_sha256"] = "0" * 64
    path.unlink()
    write_forward_record(path, {k: v for k, v in body.items() if k != "content_sha256"})
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    with pytest.raises(outcome.OutcomeJournalError, match="inconsistent"):
        outcome.outcome_status(tmp_path)


def test_duplicate_keys_rejected(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    path, _ = _write_audit(tmp_path, entry)
    path.write_text(path.read_text().replace('"schema_version":', '"schema_version": "wrong", "schema_version":', 1))
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    with pytest.raises(outcome.OutcomeJournalError, match="Duplicate outcome JSON"):
        outcome.outcome_status(tmp_path)


def test_pending_with_existing_audit_fails_closed(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    _write_audit(tmp_path, entry)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry, "PENDING")])
    with pytest.raises(outcome.OutcomeJournalError, match="before"):
        outcome.outcome_status(tmp_path)


def test_does_not_overwrite_previously_saved_outcome(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    path, _ = _write_audit(tmp_path, entry)
    before = path.read_bytes()
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    monkeypatch.setattr(outcome.subprocess, "run", lambda *args, **kwargs: pytest.fail("Should skip"))
    result = outcome.evaluate_ready(tmp_path)
    assert result.evaluated == ()
    assert path.read_bytes() == before


def test_evaluate_calls_existing_cli_with_frozen_digest(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    calls = []

    def fake_run(command, *, check):
        assert check is False
        calls.append(command)
        assert "--expect-checksum" in command
        assert command[command.index("--expect-checksum") + 1] == entry.expected_sha256
        assert command[command.index("--cost-bps") + 1] == "10"
        _write_audit(tmp_path, entry)
        return SimpleNamespace(returncode=0)

    monkeypatch.setattr(outcome.subprocess, "run", fake_run)
    result = outcome.evaluate_ready(tmp_path)
    assert len(calls) == 1
    assert len(result.evaluated) == 1
    assert result.evaluated[0].state == "COMPLETE"
    assert not result.failed


def test_subprocess_failure_reported_not_fabricated(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    monkeypatch.setattr(outcome.subprocess, "run", lambda *args, **kwargs: SimpleNamespace(returncode=8))
    result = outcome.evaluate_ready(tmp_path)
    assert result.evaluated == ()
    assert len(result.failed) == 1
    assert not outcome.audit_path(tmp_path, entry).exists()


@pytest.mark.parametrize("limit", [0, -1, 21, True, 1.0])
def test_invalid_limit_rejected(tmp_path, limit):
    with pytest.raises(outcome.OutcomeJournalError, match="limit"):
        outcome.evaluate_ready(tmp_path, limit=limit)


def test_symlink_output_directory_blocked(tmp_path, monkeypatch):
    elsewhere = tmp_path / "other"
    elsewhere.mkdir()
    (tmp_path / "outcomes").symlink_to(elsewhere, target_is_directory=True)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [])
    with pytest.raises(outcome.OutcomeJournalError, match="ordinary directory"):
        outcome.outcome_status(tmp_path)


def test_symlink_audit_blocked(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    audit = outcome.audit_path(tmp_path, entry)
    audit.parent.mkdir()
    audit.symlink_to(entry.record_path)
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    with pytest.raises(outcome.OutcomeJournalError, match="symlink"):
        outcome.outcome_status(tmp_path)


def test_mismatched_stock_identity_rejected_even_with_updated_checksum(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    path, _ = _write_audit(tmp_path, entry)
    body = json.loads(path.read_text())
    body["selected_outcomes"][0]["symbol"] = "TSLA"
    path.unlink()
    write_forward_record(path, {k: v for k, v in body.items() if k != "content_sha256"})
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    with pytest.raises(outcome.OutcomeJournalError, match="symbols or benchmark mismatch"):
        outcome.outcome_status(tmp_path)


def test_mismatched_benchmark_rejected(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    path, _ = _write_audit(tmp_path, entry)
    body = json.loads(path.read_text())
    body["benchmark_outcome"]["symbol"] = "QQQ"
    path.unlink()
    write_forward_record(path, {k: v for k, v in body.items() if k != "content_sha256"})
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    with pytest.raises(outcome.OutcomeJournalError, match="symbols or benchmark mismatch"):
        outcome.outcome_status(tmp_path)


def test_nonfinite_or_inconsistent_returns_rejected(tmp_path, monkeypatch):
    entry = _register(tmp_path)
    path, _ = _write_audit(tmp_path, entry)
    body = json.loads(path.read_text())
    body["complete_portfolio_comparison"]["excess_vs_benchmark_percentage_points"] = "NaN"
    path.unlink()
    write_forward_record(path, {k: v for k, v in body.items() if k != "content_sha256"})
    monkeypatch.setattr(outcome, "status_rows", lambda *args, **kwargs: [_row(entry)])
    with pytest.raises(outcome.OutcomeJournalError, match="finite"):
        outcome.outcome_status(tmp_path)
