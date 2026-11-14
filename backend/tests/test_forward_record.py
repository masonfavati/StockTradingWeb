"""Prospective records must never depend on future price outcomes."""

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

import pytest

from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record

T0 = datetime(2026, 11, 14, 20, 0, tzinfo=UTC)
SESSION = date(2026, 11, 13)
CANDIDATE = {"symbol": "AAPL", "last_session": "2026-11-13", "research_score": 0.6}


def sample(**changes):
    inputs = {
        "started_at": T0,
        "finished_at": T0 + timedelta(seconds=2),
        "latest_completed_session": SESSION,
        "latest_scan_session": SESSION,
        "directory_size": 50,
        "considered": 40,
        "processed": 40,
        "qualified": 1,
        "symbol_digest": universe_digest(["AAPL", "MSFT"]),
        "candidates": [CANDIDATE],
        "horizon": 20,
    }
    inputs.update(changes)
    return build_forward_record(**inputs)


def test_completed_market_record_is_a_research_only_checkpoint():
    result = sample()
    assert result["recorded_at_utc"] == "2026-11-14T20:00:02+00:00"
    assert result["adjustment"] == "all"
    assert result["shortlist"][0]["symbol"] == "AAPL"
    assert result["hypothetical_holding_sessions"] == 20
    assert "profit_probability" not in result


def test_symbol_digest_order_independent_and_identity_sensitive():
    assert universe_digest(["MSFT", "AAPL"]) == universe_digest(["AAPL", "MSFT"])
    assert universe_digest(["AAPL", "META"]) != universe_digest(["MSFT", "AAPL"])


def test_duplicate_symbols_rejected():
    with pytest.raises(ValueError, match="unique"):
        universe_digest(["AAPL", "AAPL"])


def test_partial_scan_is_refused():
    with pytest.raises(ValueError, match="incomplete"):
        sample(processed=39)


def test_future_session_is_refused():
    with pytest.raises(ValueError, match="future"):
        sample(latest_scan_session=date(2026, 11, 16))


def test_stale_candidate_is_refused():
    with pytest.raises(ValueError, match="stale"):
        sample(candidates=[{"symbol": "AAPL", "last_session": "2026-11-12", "research_score": 0.6}])


def test_no_candidate_is_recorded_only_when_fresh_session_is_verified():
    result = sample(candidates=[], qualified=0)
    assert result["shortlist"] == []
    with pytest.raises(ValueError, match="confirm current"):
        sample(candidates=[], qualified=0, latest_scan_session=None)


def test_duplicate_candidate_is_refused():
    with pytest.raises(ValueError, match="duplicate"):
        sample(candidates=[CANDIDATE, CANDIDATE], qualified=2)


def test_record_has_no_outcomes_and_writes_private_non_overwritable_file(tmp_path):
    path = tmp_path / "record.json"
    digest = write_forward_record(path, sample())
    content = json.loads(path.read_text())
    assert content["content_sha256"] == digest
    assert "outcome" not in content
    assert hashlib.sha256(json.dumps(
        {k: v for k, v in content.items() if k != "content_sha256"},
        sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")).hexdigest() == digest
    assert path.stat().st_mode & 0o777 == 0o600
    with pytest.raises(FileExistsError):
        write_forward_record(path, sample())


def test_nonfinite_research_score_refused():
    with pytest.raises(ValueError, match="Out of range float values"):
        sample(candidates=[{"symbol": "AAPL", "last_session": "2026-11-13", "research_score": float('nan')}])


def test_naive_record_timestamp_refused():
    with pytest.raises(ValueError, match="time zone"):
        sample(started_at=datetime(2026, 11, 14, 20))


def test_horizon_outside_range_refused():
    with pytest.raises(ValueError, match="Horizon"):
        sample(horizon=0)
