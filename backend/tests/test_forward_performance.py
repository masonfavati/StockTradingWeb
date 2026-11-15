"""Cumulative forward reporting must stay descriptive, complete and immutable."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.analysis import forward_performance as performance
from app.analysis.forward_evaluation import EvaluationWindow, build_outcome_audit
from app.analysis.forward_journal import StatusRow, register
from app.analysis.forward_outcomes import OutcomeStatus, _status, audit_path
from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record
from app.market_data.history_client import DailyBar


def _make_entry(
    root: Path, signal: date, *, horizon: int = 20, rule: str | None = None,
    symbol: str | tuple[str, ...] | None = "AAPL",
):
    timestamp = datetime.combine(signal + timedelta(days=1), datetime.min.time(), tzinfo=UTC) + timedelta(hours=22)
    symbols = () if symbol is None else (symbol,) if isinstance(symbol, str) else symbol
    candidates = [
        {"symbol": name, "last_session": signal.isoformat(), "research_score": 0.75}
        for name in symbols
    ]
    body = build_forward_record(
        started_at=timestamp - timedelta(minutes=1), finished_at=timestamp,
        latest_completed_session=signal, latest_scan_session=signal,
        directory_size=30, considered=28, processed=28, qualified=len(candidates),
        symbol_digest=universe_digest(["AAPL", "MSFT", "SPY"]),
        candidates=candidates, horizon=horizon,
    )
    if rule is not None:
        body["research_rule"] = rule
    path = root / f"checkpoint_{signal}_{horizon}_{rule or 'default'}.json"
    digest = write_forward_record(path, body)
    entry, created = register(root, path, checksum=digest)
    assert created
    return entry


def _bar(symbol: str, session: date, opening: str) -> DailyBar:
    price = Decimal(opening)
    return DailyBar(
        symbol=symbol, session_date=session,
        bar_timestamp=datetime.combine(session, datetime.min.time(), tzinfo=UTC),
        open_price=price, high_price=price + 1, low_price=price - 1,
        close_price=price, volume=100_000, trade_count=100, vwap=None,
    )


def _make_status(
    root: Path, entry, *, state: str = "COMPLETE",
    entry_date: date = date(2026, 11, 16),
    exit_date: date = date(2026, 12, 15),
    selected_exit: str = "110", spy_exit: str = "205",
) -> OutcomeStatus:
    ready = StatusRow(entry, "READY", 21, 21)
    if state in {"PENDING", "READY"}:
        return OutcomeStatus(StatusRow(entry, state, 0, 21), state, audit_path(root, entry))
    window = EvaluationWindow(21, 21, entry_date, exit_date)
    bars = [_bar("SPY", entry_date, "200"), _bar("SPY", exit_date, spy_exit)]
    if state == "COMPLETE":
        for symbol in entry.checkpoint.shortlist:
            bars.extend((_bar(symbol, entry_date, "100"), _bar(symbol, exit_date, selected_exit)))
    audit = build_outcome_audit(
        entry.checkpoint, window, bars=bars, invalid_symbols=set(),
        cost_bps_per_side=Decimal(10),
        evaluated_at=datetime(2027, 1, 8, 22, tzinfo=UTC),
    )
    expected = {
        "COMPLETE": "complete", "INCOMPLETE": "incomplete_outcomes", "NO_SELECTION": "no_selection"
    }[state]
    assert audit["status"] == expected
    path = audit_path(root, entry)
    path.parent.mkdir(parents=True, exist_ok=True)
    write_forward_record(path, audit)
    return _status(root, ready)


def _report(root: Path, monkeypatch, *rows: OutcomeStatus):
    monkeypatch.setattr(performance, "outcome_status", lambda *args, **kwargs: list(rows))
    return performance.build_performance_report(root, now=datetime(2027, 1, 10, tzinfo=UTC))


def test_empty_journal_does_not_claim_performance(tmp_path, monkeypatch):
    report = _report(tmp_path, monkeypatch)
    assert report["registered_checkpoints"] == 0
    assert report["groups"] == []
    assert report["status_counts"]["COMPLETE"] == 0


def test_pending_journal_retained_without_return_metrics(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    report = _report(tmp_path, monkeypatch, _make_status(tmp_path, entry, state="PENDING"))
    group = report["groups"][0]
    assert group["registered_checkpoints"] == 1
    assert group["status_counts"]["PENDING"] == 1
    assert group["metrics"] is None
    assert group["completed_observations"] == []
    assert not (tmp_path / "outcomes").exists()


def test_ready_still_does_not_claim_outcome(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    report = _report(tmp_path, monkeypatch, _make_status(tmp_path, entry, state="READY"))
    assert report["groups"][0]["status_counts"]["READY"] == 1
    assert report["groups"][0]["metrics"] is None


def test_complete_observation_uses_frozen_price_math(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    report = _report(tmp_path, monkeypatch, item)
    group = report["groups"][0]
    metrics = group["metrics"]
    assert metrics["complete_windows"] == 1
    assert metrics["positive_selected_windows"] == 1
    assert metrics["windows_beating_spy"] == 1
    assert Decimal(metrics["mean_selected_net_pct"]) > Decimal(9)
    assert Decimal(metrics["mean_spy_net_pct"]) > Decimal(2)
    assert group["completed_observations"][0]["outcome_sha256"] == item.audit_sha256


def test_incomplete_outcome_counted_but_not_averaged(tmp_path, monkeypatch):
    complete = _make_entry(tmp_path, date(2026, 11, 13))
    incomplete = _make_entry(tmp_path, date(2026, 11, 16))
    report = _report(tmp_path, monkeypatch,
                     _make_status(tmp_path, complete),
                     _make_status(tmp_path, incomplete, state="INCOMPLETE",
                                  entry_date=date(2026, 11, 17), exit_date=date(2026, 12, 16)))
    group = report["groups"][0]
    assert group["registered_checkpoints"] == 2
    assert group["status_counts"]["INCOMPLETE"] == 1
    assert group["metrics"]["complete_windows"] == 1


def test_no_selection_excluded_from_comparisons(tmp_path, monkeypatch):
    empty = _make_entry(tmp_path, date(2026, 11, 13), symbol=None)
    report = _report(tmp_path, monkeypatch, _make_status(tmp_path, empty, state="NO_SELECTION"))
    assert report["groups"][0]["status_counts"]["NO_SELECTION"] == 1
    assert report["groups"][0]["metrics"] is None


def test_overlapping_windows_are_counted_but_not_called_independent(tmp_path, monkeypatch):
    first = _make_entry(tmp_path, date(2026, 11, 13))
    second = _make_entry(tmp_path, date(2026, 11, 16))
    report = _report(tmp_path, monkeypatch,
                     _make_status(tmp_path, first),
                     _make_status(tmp_path, second, entry_date=date(2026, 11, 17),
                                  exit_date=date(2026, 12, 16)))
    overlap = report["groups"][0]["overlap"]
    assert overlap == {
        "overlapping_pairs": 1,
        "observations_with_overlap": 2,
        "maximum_simultaneous_windows": 2,
        "maximum_date_disjoint_windows": 1,
    }


def test_open_to_open_touching_windows_do_not_overlap(tmp_path):
    def make(start: date, end: date) -> performance.VerifiedObservation:
        return performance.VerifiedObservation(
        signal=start - timedelta(days=1), entry=start, exit=end,
        selected_pct=Decimal(1), benchmark_pct=Decimal(1), excess_pp=Decimal(0),
        profitable_stocks=1, total_stocks=1, checkpoint_sha256="a" * 64,
        outcome_sha256="b" * 64,
    )
    assert performance._overlap_diagnostics([
        make(date(2026, 11, 16), date(2026, 12, 15)),
        make(date(2026, 12, 15), date(2027, 1, 15)),
    ]) == {
        "overlapping_pairs": 0,
        "observations_with_overlap": 0,
        "maximum_simultaneous_windows": 1,
        "maximum_date_disjoint_windows": 2,
    }


def test_group_different_horizons_never_pooled(tmp_path, monkeypatch):
    first = _make_entry(tmp_path, date(2026, 11, 13), horizon=20)
    second = _make_entry(tmp_path, date(2026, 11, 13), horizon=5)
    report = _report(tmp_path, monkeypatch,
                     _make_status(tmp_path, first),
                     _make_status(tmp_path, second))
    assert [group["holding_sessions"] for group in report["groups"]] == [5, 20]
    assert all(group["metrics"]["complete_windows"] == 1 for group in report["groups"])


def test_group_different_research_rules_never_pooled(tmp_path, monkeypatch):
    first = _make_entry(tmp_path, date(2026, 11, 13), rule="model-v1")
    second = _make_entry(tmp_path, date(2026, 11, 13), rule="model-v2")
    report = _report(tmp_path, monkeypatch,
                     _make_status(tmp_path, first),
                     _make_status(tmp_path, second))
    assert len(report["groups"]) == 2
    assert {group["research_rule"] for group in report["groups"]} == {"model-v1", "model-v2"}


def test_descriptive_dispersion_of_identical_returns_is_zero(tmp_path, monkeypatch):
    first = _make_entry(tmp_path, date(2026, 11, 13))
    second = _make_entry(tmp_path, date(2026, 11, 16))
    report = _report(tmp_path, monkeypatch,
                     _make_status(tmp_path, first),
                     _make_status(tmp_path, second, entry_date=date(2026, 11, 17),
                                  exit_date=date(2026, 12, 16)))
    assert report["groups"][0]["metrics"]["descriptive_excess_dispersion_pp"] == "0.0000"


def test_negative_returns_preserved_without_picking_winners(tmp_path, monkeypatch):
    first = _make_entry(tmp_path, date(2026, 11, 13))
    second = _make_entry(tmp_path, date(2026, 11, 16))
    report = _report(tmp_path, monkeypatch,
                     _make_status(tmp_path, first),
                     _make_status(tmp_path, second, selected_exit="85",
                                  entry_date=date(2026, 11, 17), exit_date=date(2026, 12, 16)))
    metrics = report["groups"][0]["metrics"]
    assert metrics["positive_selected_windows"] == 1
    assert metrics["windows_beating_spy"] == 1
    assert Decimal(metrics["worst_paired_excess_pp"]) < 0


def test_rehashed_wrong_net_return_rejected(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    body = json.loads(item.audit_path.read_text())
    body["selected_outcomes"][0]["net_return_pct"] = "200.0000"
    item.audit_path.unlink()
    write_forward_record(item.audit_path, {
        key: value for key, value in body.items() if key != "content_sha256"
    })
    with pytest.raises(performance.PerformanceReportError, match="disagrees"):
        _report(tmp_path, monkeypatch, item)


def test_rehashed_wrong_spy_return_rejected(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    body = json.loads(item.audit_path.read_text())
    body["benchmark_outcome"]["net_return_pct"] = "50.0000"
    item.audit_path.unlink()
    write_forward_record(item.audit_path, {
        key: value for key, value in body.items() if key != "content_sha256"
    })
    with pytest.raises(performance.PerformanceReportError, match="disagrees"):
        _report(tmp_path, monkeypatch, item)


def test_rehashed_wrong_win_count_rejected(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    body = json.loads(item.audit_path.read_text())
    body["complete_portfolio_comparison"]["selected_winners_after_costs"] = 0
    item.audit_path.unlink()
    write_forward_record(item.audit_path, {
        key: value for key, value in body.items() if key != "content_sha256"
    })
    with pytest.raises(performance.PerformanceReportError, match="disagrees"):
        _report(tmp_path, monkeypatch, item)


def test_invalid_time_rejected_before_accessing_journal(tmp_path, monkeypatch):
    monkeypatch.setattr(performance, "outcome_status", lambda *args, **kwargs: pytest.fail("shouldn't query"))
    with pytest.raises(performance.PerformanceReportError, match="time zone"):
        performance.build_performance_report(tmp_path, now=datetime(2026, 11, 14))


def test_report_does_not_modify_source_checkpoint_or_outcome(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    checkpoint_before = entry.record_path.read_bytes()
    audit_before = item.audit_path.read_bytes()
    _report(tmp_path, monkeypatch, item)
    assert entry.record_path.read_bytes() == checkpoint_before
    assert item.audit_path.read_bytes() == audit_before


def test_return_dates_must_be_forward(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    body = json.loads(item.audit_path.read_text())
    body["entry_session"] = "2026-11-12"
    item.audit_path.unlink()
    write_forward_record(item.audit_path, {
        key: value for key, value in body.items() if key != "content_sha256"
    })
    with pytest.raises(performance.PerformanceReportError, match="strictly forward"):
        _report(tmp_path, monkeypatch, item)


def test_json_serializable_and_schema_version(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    report = _report(tmp_path, monkeypatch, _make_status(tmp_path, entry))
    assert report["schema_version"] == performance.REPORT_SCHEMA
    assert json.loads(json.dumps(report)) == report
    assert "independent trials" in " ".join(report["warnings"])


def test_audit_with_invalid_cost_blocks_report(tmp_path, monkeypatch):
    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    body = json.loads(item.audit_path.read_text())
    body["assumed_cost_bps_each_side"] = "0"
    item.audit_path.unlink()
    write_forward_record(item.audit_path, {
        key: value for key, value in body.items() if key != "content_sha256"
    })
    from app.analysis.forward_outcomes import OutcomeJournalError
    with pytest.raises(OutcomeJournalError, match="inconsistent"):
        _report(tmp_path, monkeypatch, item)


def test_existing_journal_accepts_legitimate_one_unit_rounding_difference(tmp_path):
    """Two rounding steps must not make a valid full portfolio look corrupt."""
    from app.analysis.forward_outcomes import _read_existing

    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    audit = json.loads(item.audit_path.read_text())
    # For real 2-stock portfolios, this can occur when the unrounded mean
    # straddles a .00005 percentage-point tie, unlike the displayed mean.
    comparison = audit["complete_portfolio_comparison"]
    comparison["selected_equal_weight_net_return_pct"] = "1.0000"
    comparison["benchmark_net_return_pct"] = "0.0001"
    comparison["excess_vs_benchmark_percentage_points"] = "1.0000"
    item.audit_path.unlink()
    write_forward_record(item.audit_path, {
        key: value for key, value in audit.items() if key != "content_sha256"
    })
    assert _read_existing(item.audit_path, entry)["status"] == "complete"


def test_journal_still_rejects_materially_inconsistent_comparison(tmp_path):
    from app.analysis.forward_outcomes import OutcomeJournalError, _read_existing

    entry = _make_entry(tmp_path, date(2026, 11, 13))
    item = _make_status(tmp_path, entry)
    audit = json.loads(item.audit_path.read_text())
    comparison = audit["complete_portfolio_comparison"]
    comparison["excess_vs_benchmark_percentage_points"] = "98.0000"
    item.audit_path.unlink()
    write_forward_record(item.audit_path, {
        key: value for key, value in audit.items() if key != "content_sha256"
    })
    with pytest.raises(OutcomeJournalError, match="inconsistent"):
        _read_existing(item.audit_path, entry)


def test_cli_plaintext_pending_report_avoids_returns(monkeypatch, capsys, tmp_path):
    import sys

    from app.analysis import forward_performance_cli as cli

    entry = _make_entry(tmp_path, date(2026, 11, 13))
    report = _report(tmp_path, monkeypatch, _make_status(tmp_path, entry, state="PENDING"))
    monkeypatch.setattr(cli, "build_performance_report", lambda *args, **kwargs: report)
    monkeypatch.setattr(sys, "argv", ["forward_performance_cli", "--dir", str(tmp_path)])
    cli.main()
    output = capsys.readouterr().out
    assert "PENDING: 1" in output
    assert "NO COMPLETE OUTCOMES" in output
    assert "Mean paired excess:" not in output


def test_cli_json_is_machine_readable(monkeypatch, capsys, tmp_path):
    import sys

    from app.analysis import forward_performance_cli as cli

    report = _report(tmp_path, monkeypatch)
    monkeypatch.setattr(cli, "build_performance_report", lambda *args, **kwargs: report)
    monkeypatch.setattr(sys, "argv", ["forward_performance_cli", "--dir", str(tmp_path), "--json"])
    cli.main()
    assert json.loads(capsys.readouterr().out) == report


def test_genuine_multi_stock_half_tick_rounding_is_accepted(tmp_path, monkeypatch):
    """The real audit builder can round displayed mean and excess differently."""
    entry = _make_entry(tmp_path, date(2026, 11, 13), symbol=("AAPL", "MSFT"))
    opening = date(2026, 11, 16)
    closing = date(2026, 12, 15)
    window = EvaluationWindow(21, 21, opening, closing)
    friction = (Decimal(1) + Decimal("0.001")) / (Decimal(1) - Decimal("0.001"))

    def exit_for_return(pct: str) -> str:
        return str(Decimal(100) * (Decimal(1) + Decimal(pct) / 100) * friction)

    bars = []
    for symbol, desired_pct in (("AAPL", "1.0000"), ("MSFT", "1.0001"),
                                ("SPY", "0.0001")):
        bars.extend((_bar(symbol, opening, "100"),
                     _bar(symbol, closing, exit_for_return(desired_pct))))
    body = build_outcome_audit(
        entry.checkpoint, window, bars=bars, invalid_symbols=set(),
        cost_bps_per_side=Decimal(10),
        evaluated_at=datetime(2027, 1, 8, 22, tzinfo=UTC),
    )
    comparison = body["complete_portfolio_comparison"]
    assert comparison["selected_equal_weight_net_return_pct"] == "1.0000"
    assert comparison["benchmark_net_return_pct"] == "0.0001"
    assert comparison["excess_vs_benchmark_percentage_points"] == "1.0000"
    path = audit_path(tmp_path, entry)
    path.parent.mkdir(exist_ok=True)
    write_forward_record(path, body)
    item = _status(tmp_path, StatusRow(entry, "READY", 21, 21))
    report = _report(tmp_path, monkeypatch, item)
    assert report["groups"][0]["metrics"]["mean_paired_excess_pp"] == "1.0000"
