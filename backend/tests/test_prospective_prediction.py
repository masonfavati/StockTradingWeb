"""Prospective predictions must be truly chronological, verified and gated."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.analysis import prospective_prediction as model
from app.analysis.forward_evaluation import EvaluationWindow, build_outcome_audit
from app.analysis.forward_journal import StatusRow, register
from app.analysis.forward_outcomes import _status, audit_path
from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record
from app.market_data.history_client import DailyBar

START = date(2026, 11, 13)
FEATURE = (0.5, 0.8, 0.35, -0.2, 0.9, 0.75)


def scanner_candidate(symbol: str = "AAA") -> dict:
    return {
        "symbol": symbol, "name": f"{symbol} Common Stock", "last_session": START.isoformat(),
        "adjusted_close": 25.0, "return_20d_pct": 8.0, "return_60d_pct": 25.0,
        "annualized_volatility_pct": 30.0, "drawdown_60d_pct": -8.0,
        "approx_daily_dollar_volume": 10_000_000.0, "research_score": 0.9,
    }


def synthetic_windows(count: int, stock_count: int = 10, duration: int = 20) -> list[model.Window]:
    result = []
    for index in range(count):
        signal = START + timedelta(days=index)
        exit_day = signal + timedelta(days=duration)
        rows = tuple(model.Observation(
            f"S{position:02}", signal, signal + timedelta(days=1), exit_day,
            FEATURE if position % 2 else (-0.5, 0.8, 0.3, -0.2, 0.9, 0.75),
            position % 2, 2.0 if position % 2 else -2.0,
        ) for position in range(stock_count))
        result.append(model.Window(signal, exit_day, rows, "a" * 64, "b" * 64))
    return result


def _bar(ticker: str, day: date, opening: str) -> DailyBar:
    price = Decimal(opening)
    return DailyBar(
        symbol=ticker, session_date=day,
        bar_timestamp=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
        open_price=price, high_price=price + 1, low_price=price - 1,
        close_price=price, volume=100_000, trade_count=100, vwap=None,
    )


def saved_complete(root: Path):
    signal = START
    captured = datetime(2026, 11, 14, 5, tzinfo=UTC)
    frozen = build_forward_record(
        started_at=captured - timedelta(minutes=1), finished_at=captured,
        latest_completed_session=signal, latest_scan_session=signal,
        directory_size=100, considered=99, processed=99, qualified=1,
        symbol_digest=universe_digest(["AAA", "SPY"]),
        candidates=[scanner_candidate()], horizon=model.HORIZON,
    )
    path = root / "frozen.json"
    sha = write_forward_record(path, frozen)
    entry, _new = register(root, path, checksum=sha)
    entered = date(2026, 11, 16)
    exited = date(2026, 12, 15)
    audit = build_outcome_audit(
        entry.checkpoint, EvaluationWindow(21, 21, entered, exited),
        bars=[
            _bar("AAA", entered, "100"), _bar("AAA", exited, "115"),
            _bar("SPY", entered, "200"), _bar("SPY", exited, "210"),
        ],
        invalid_symbols=set(), cost_bps_per_side=Decimal(10),
        evaluated_at=datetime(2026, 12, 16, 12, tzinfo=UTC),
    )
    outcome = audit_path(root, entry)
    outcome.parent.mkdir(parents=True, exist_ok=True)
    write_forward_record(outcome, audit)
    status = _status(root, StatusRow(entry, "READY", 21, 21))
    assert status.state == "COMPLETE"
    return path, status


def test_empty_report_never_claims_prediction(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(model, "outcome_status", lambda *a, **kw: [])
    report = model.build_prediction_report(tmp_path)
    assert report["status"] == "insufficient_evidence"
    assert report["walk_forward"]["validation_windows"] == 0
    assert report["walk_forward"]["brier_score"] is None
    assert not report["walk_forward"]["research_gate_passed"]


def test_a_real_pinned_and_audited_outcome_supplies_one_example(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    _path, status = saved_complete(tmp_path)
    monkeypatch.setattr(model, "outcome_status", lambda *a, **kw: [status])
    windows, counts = model.load_verified_windows(tmp_path)
    assert counts["COMPLETE"] == 1
    assert len(windows) == 1
    sample = windows[0].observations[0]
    assert sample.symbol == "AAA"
    assert sample.beat_spy == 1
    assert sample.signal == START
    assert sample.entry > sample.signal
    assert sample.exit > sample.entry
    assert len(sample.features) == len(model.FEATURES)
    assert model.build_prediction_report(tmp_path)["status"] == "insufficient_evidence"


def test_frozen_features_tampering_blocks_training(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    source, status = saved_complete(tmp_path)
    monkeypatch.setattr(model, "outcome_status", lambda *a, **kw: [status])
    source.write_text(source.read_text().replace('"return_20d_pct": 8.0', '"return_20d_pct": 18.0'))
    with pytest.raises(ValueError, match="SHA-256"):
        model.load_verified_windows(tmp_path)


def test_unsupported_horizon_never_enters_training(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _path, status = saved_complete(tmp_path)
    altered = replace(status.row.entry.checkpoint, horizon=10)
    entry = replace(status.row.entry, checkpoint=altered)
    changed = replace(status, row=replace(status.row, entry=entry))
    monkeypatch.setattr(model, "outcome_status", lambda *a, **kw: [changed])
    windows, counts = model.load_verified_windows(tmp_path)
    assert windows == []
    assert counts["COMPLETE"] == 1


@pytest.mark.parametrize("value", [None, True, float("inf"), float("nan"), "10", 10**20])
def test_missing_or_invalid_feature_is_rejected(value: object) -> None:
    row = scanner_candidate()
    row["return_20d_pct"] = value
    with pytest.raises(model.PredictionEvidenceError):
        model._features(row)


@pytest.mark.parametrize("volume", [-1.0, 0.0])
def test_nonpositive_volume_never_enters_model(volume: float) -> None:
    candidate = scanner_candidate()
    candidate["approx_daily_dollar_volume"] = volume
    with pytest.raises(model.PredictionEvidenceError):
        model._features(candidate)


def test_training_with_only_one_class_is_blocked() -> None:
    windows = synthetic_windows(31)
    negatives = [model.Window(w.signal, w.exit, tuple(
        model.Observation(r.symbol, r.signal, r.entry, r.exit, r.features, 0, -1)
        for r in w.observations), w.checkpoint_sha256, w.outcome_sha256) for w in windows]
    assert not model._can_fit(negatives)
    with pytest.raises(model.PredictionEvidenceError):
        model._fit([])


def test_walkforward_never_uses_overlapping_labels(monkeypatch: pytest.MonkeyPatch) -> None:
    windows = synthetic_windows(57)
    original = model._fit
    trained_exit_dates: list[date] = []

    def assert_earlier(rows: list[model.Observation]) -> list[float]:
        trained_exit_dates.append(max(row.exit for row in rows))
        return original(rows)

    monkeypatch.setattr(model, "_fit", assert_earlier)
    report = model.evaluate_walk_forward(windows)
    assert report["validation_windows"] == len(trained_exit_dates)
    assert report["validation_windows"] > 0
    sampled = [window.signal for window in windows if
               window.signal.toordinal() % model.VALIDATION_CALENDAR_STRIDE == 0
               and sum(prior.exit < window.signal for prior in windows) >= model.MIN_TRAIN_WINDOWS]
    assert len(sampled) == len(trained_exit_dates)
    assert all(exit_day < signal for exit_day, signal in zip(trained_exit_dates, sampled, strict=True))
    assert report["nonoverlapping_validation_windows"] >= 1


def test_insample_training_cannot_pass_research_gate() -> None:
    report = model.evaluate_walk_forward(synthetic_windows(30))
    assert report["validation_windows"] == 0
    assert not any(report["checks"].values())


def test_prediction_is_withheld_if_gate_or_history_missing() -> None:
    candidate = scanner_candidate()
    empty = model.unavailable_prediction(["AAA"])
    assert empty["approved_symbols"] == []
    assert empty["status"] == "unavailable"
    review = model.review_prediction([candidate], START.isoformat(), [], {
        "status": "research_gate_passed",
    })
    assert review["approved_symbols"] == []
    assert review["status"] == "insufficient_training_before_signal"


def test_future_validation_cannot_be_used_to_approve_past_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = synthetic_windows(45)
    called = False

    def never_called(_windows: object) -> dict:
        nonlocal called
        called = True
        return {"research_gate_passed": True}

    monkeypatch.setattr(model, "evaluate_walk_forward", never_called)
    review = model.review_prediction([scanner_candidate()], START.isoformat(), windows, {
        "status": "research_gate_passed",
    })
    assert review["approved_symbols"] == []
    assert not called


def test_failed_past_only_validation_cannot_publish_probability(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = synthetic_windows(35, duration=1)
    monkeypatch.setattr(model, "evaluate_walk_forward", lambda _rows: {"research_gate_passed": False})
    future_signal = START + timedelta(days=100)
    candidate = scanner_candidate()
    candidate["last_session"] = future_signal.isoformat()
    review = model.review_prediction([candidate], future_signal.isoformat(), windows, {
        "status": "research_gate_passed",
    })
    assert review["status"] == "not_validated_before_signal"
    assert review["scores"] == []


def test_successful_gate_requires_minimum_probability_and_prior_lift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows = synthetic_windows(35, duration=1)
    monkeypatch.setattr(model, "evaluate_walk_forward", lambda _rows: {"research_gate_passed": True})
    monkeypatch.setattr(model, "_fit", lambda _rows: [0.8, 0, 0, 0, 0, 0, 0])
    future_signal = START + timedelta(days=100)
    candidate = scanner_candidate()
    candidate["last_session"] = future_signal.isoformat()
    review = model.review_prediction([candidate], future_signal.isoformat(), windows, {
        "status": "research_gate_passed", "source_sha256": "a" * 64,
    })
    assert review["status"] == "research_gate_passed"
    assert review["approved_symbols"] == ["AAA"]
    assert review["scores"][0]["estimated_probability_beating_spy"] > 0.55
    assert review["proposed_slot_count"] == 1


def test_validation_results_never_describe_guaranteed_returns() -> None:
    report = model.evaluate_walk_forward(synthetic_windows(35))
    assert not report["research_gate_passed"]
    assert report["top_two_mean_excess_vs_spy_pp"] is None


def test_fixed_fit_is_deterministic() -> None:
    windows = synthetic_windows(30)
    rows = model._training_rows(windows)
    assert model._fit(rows) == model._fit(rows)


def test_no_unbounded_predictions_from_missing_scanner_features() -> None:
    candidate = scanner_candidate()
    candidate.pop("return_60d_pct")
    with pytest.raises(model.PredictionEvidenceError):
        model._features(candidate)
