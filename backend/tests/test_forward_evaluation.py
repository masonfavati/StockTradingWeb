"""Frozen forward research must not become a hindsight-optimized portfolio."""

import json
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest

from app.analysis.forward_evaluation import (
    ForwardEvaluationError,
    build_outcome_audit,
    evaluation_window,
    load_checkpoint,
    validate_cost,
)
from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record
from app.market_data.history_client import DailyBar

SIGNAL = date(2026, 11, 13)
T0 = datetime(2026, 11, 14, 22, tzinfo=UTC)


def _write_checkpoint(tmp_path, candidates=("AAPL", "MSFT")):
    record = build_forward_record(
        started_at=T0 - timedelta(minutes=1),
        finished_at=T0,
        latest_completed_session=SIGNAL,
        latest_scan_session=SIGNAL,
        directory_size=50,
        considered=40,
        processed=40,
        qualified=len(candidates),
        symbol_digest=universe_digest(["AAPL", "MSFT", "SPY"]),
        candidates=[
            {"symbol": symbol, "last_session": SIGNAL.isoformat(), "research_score": 0.6}
            for symbol in candidates
        ],
        horizon=20,
    )
    path = tmp_path / "forward.json"
    digest = write_forward_record(path, record)
    return path, digest


def _checkpoint(tmp_path, candidates=("AAPL", "MSFT")):
    path, digest = _write_checkpoint(tmp_path, candidates)
    return load_checkpoint(path, expected_checksum=digest)


def _calendar(days: int = 25):
    future = []
    day = SIGNAL + timedelta(days=1)
    while len(future) < days:
        if day.weekday() < 5:
            future.append(day)
        day += timedelta(days=1)
    return {SIGNAL, *future}, future


def _mature(tmp_path, candidates=("AAPL", "MSFT")):
    cp = _checkpoint(tmp_path, candidates)
    sessions, future = _calendar()
    window = evaluation_window(cp, sessions=sessions, completed_through=future[-1])
    return cp, window


def _bar(symbol: str, when: date, open_price: str) -> DailyBar:
    price = Decimal(open_price)
    return DailyBar(
        symbol=symbol,
        session_date=when,
        bar_timestamp=datetime.combine(when, datetime.min.time(), tzinfo=UTC),
        open_price=price,
        high_price=price + 1,
        low_price=price - 1,
        close_price=price,
        volume=100_000,
        trade_count=100,
        vwap=None,
    )


def _prices(window):
    return [
        _bar("AAPL", window.entry_session, "50"),
        _bar("AAPL", window.exit_session, "60"),
        _bar("MSFT", window.entry_session, "100"),
        _bar("MSFT", window.exit_session, "90"),
        _bar("SPY", window.entry_session, "200"),
        _bar("SPY", window.exit_session, "210"),
    ]


def _audit(cp, window, bars, **changes):
    args = {
        "invalid_symbols": set(),
        "cost_bps_per_side": Decimal(10),
        "evaluated_at": T0 + timedelta(days=45),
    }
    args.update(changes)
    return build_outcome_audit(cp, window, bars=bars, **args)


def test_checkpoint_round_trip_verifies_original_checksum(tmp_path):
    path, digest = _write_checkpoint(tmp_path)
    frozen = load_checkpoint(path, expected_checksum=digest)
    assert frozen.shortlist == ("AAPL", "MSFT")
    assert frozen.horizon == 20
    assert frozen.signal_session == SIGNAL
    assert frozen.content_sha256 == digest


def test_modifying_checkpoint_causes_hash_mismatch(tmp_path):
    path, digest = _write_checkpoint(tmp_path)
    tampered = json.loads(path.read_text())
    tampered["shortlist"][0]["symbol"] = "TSLA"
    path.write_text(json.dumps(tampered))
    with pytest.raises(ForwardEvaluationError, match="mismatch"):
        load_checkpoint(path, expected_checksum=digest)


def test_independently_supplied_wrong_checksum_rejected(tmp_path):
    path, _digest = _write_checkpoint(tmp_path)
    with pytest.raises(ForwardEvaluationError, match="mismatch"):
        load_checkpoint(path, expected_checksum="a" * 64)


def test_duplicate_json_keys_rejected(tmp_path):
    path, digest = _write_checkpoint(tmp_path)
    source = path.read_text()
    path.write_text(source.replace('"schema_version":', '"schema_version": "bad", "schema_version":', 1))
    with pytest.raises(ForwardEvaluationError, match="Duplicate JSON key"):
        load_checkpoint(path, expected_checksum=digest)


def test_short_horizon_does_not_calculate_returns(tmp_path):
    cp = _checkpoint(tmp_path)
    sessions, future = _calendar(10)
    window = evaluation_window(cp, sessions=sessions, completed_through=future[-1])
    assert not window.is_mature
    assert window.observed_future_sessions == 10
    assert window.required_future_sessions == 21
    assert window.exit_session is None
    with pytest.raises(ForwardEvaluationError, match="before the exit"):
        _audit(cp, window, [])


def test_exact_session_count_and_open_to_open_horizon(tmp_path):
    cp = _checkpoint(tmp_path)
    sessions, future = _calendar(21)
    window = evaluation_window(cp, sessions=sessions, completed_through=future[-1])
    assert window.is_mature
    assert window.entry_session == future[0]
    assert window.exit_session == future[20]


def test_one_session_too_few_stays_pending(tmp_path):
    cp = _checkpoint(tmp_path)
    sessions, future = _calendar(20)
    assert not evaluation_window(cp, sessions=sessions, completed_through=future[-1]).is_mature


def test_signal_must_exist_in_verified_calendar(tmp_path):
    cp = _checkpoint(tmp_path)
    _, future = _calendar(21)
    with pytest.raises(ForwardEvaluationError, match="verified exchange"):
        evaluation_window(cp, sessions=set(future), completed_through=future[-1])


def test_future_calendar_dates_are_rejected(tmp_path):
    cp = _checkpoint(tmp_path)
    sessions, future = _calendar(21)
    with pytest.raises(ForwardEvaluationError, match="after the completed"):
        evaluation_window(cp, sessions=sessions, completed_through=future[18])


def test_record_created_on_entry_day_rejected(tmp_path):
    cp = _checkpoint(tmp_path)
    sessions, future = _calendar(21)
    cp = type(cp)(
        content_sha256=cp.content_sha256,
        recorded_at_utc=datetime(2026, 11, 16, 14, tzinfo=UTC),
        signal_session=cp.signal_session,
        horizon=cp.horizon,
        shortlist=cp.shortlist,
        research_rule=cp.research_rule,
    )
    with pytest.raises(ForwardEvaluationError, match="before the proposed"):
        evaluation_window(cp, sessions=sessions, completed_through=future[-1])


def test_full_equal_weight_comparison_and_costs(tmp_path):
    cp, window = _mature(tmp_path)
    report = _audit(cp, window, _prices(window))
    assert report["status"] == "complete"
    assert report["entry_exit_price_type"] == "daily_open"
    assert report["outcome_adjustment"] == "split"
    assert report["holding_sessions"] == 20
    assert report["complete_portfolio_comparison"] is not None
    assert report["selected_outcomes"][0]["gross_return_pct"] == "20.0000"
    assert report["selected_outcomes"][0]["net_return_pct"] != "20.0000"
    assert report["selected_outcomes"][1]["gross_return_pct"] == "-10.0000"
    assert report["benchmark_outcome"]["gross_return_pct"] == "5.0000"
    assert report["complete_portfolio_comparison"]["selected_winners_after_costs"] == 1


def test_cost_is_charged_on_both_sides(tmp_path):
    cp, window = _mature(tmp_path)
    bars = _prices(window)
    raw = _audit(cp, window, bars, cost_bps_per_side=Decimal(0))
    costed = _audit(cp, window, bars, cost_bps_per_side=Decimal(10))
    assert Decimal(raw["selected_outcomes"][0]["net_return_pct"]) == Decimal(20)
    assert Decimal(costed["selected_outcomes"][0]["net_return_pct"]) < Decimal(20)
    assert costed["assumed_cost_bps_each_side"] == "10"


def test_missing_exit_blocks_complete_portfolio_claim(tmp_path):
    cp, window = _mature(tmp_path)
    bars = [bar for bar in _prices(window) if not (bar.symbol == "MSFT" and bar.session_date == window.exit_session)]
    result = _audit(cp, window, bars)
    assert result["status"] == "incomplete_outcomes"
    assert result["selected_outcomes"][1]["status"] == "missing_exit_open"
    assert result["complete_portfolio_comparison"] is None


def test_missing_entry_blocks_complete_portfolio_claim(tmp_path):
    cp, window = _mature(tmp_path)
    bars = [bar for bar in _prices(window) if not (bar.symbol == "MSFT" and bar.session_date == window.entry_session)]
    result = _audit(cp, window, bars)
    assert result["selected_outcomes"][1]["status"] == "missing_entry_open"
    assert result["complete_portfolio_comparison"] is None


def test_missing_benchmark_blocks_outperformance_claim(tmp_path):
    cp, window = _mature(tmp_path)
    bars = [bar for bar in _prices(window) if bar.symbol != "SPY"]
    result = _audit(cp, window, bars)
    assert result["benchmark_outcome"]["status"] == "missing_entry_open"
    assert result["complete_portfolio_comparison"] is None


def test_quarantined_stock_is_never_replaced_with_next_ranked_candidate(tmp_path):
    cp, window = _mature(tmp_path)
    result = _audit(cp, window, _prices(window), invalid_symbols={"AAPL"})
    assert result["status"] == "incomplete_outcomes"
    assert result["selected_outcomes"][0]["status"] == "invalid_core_bar"
    assert [row["symbol"] for row in result["selected_outcomes"]] == ["AAPL", "MSFT"]
    assert result["complete_portfolio_comparison"] is None


def test_duplicate_outcome_bar_blocks_portfolio_result(tmp_path):
    cp, window = _mature(tmp_path)
    bars = _prices(window) + [_bar("SPY", window.entry_session, "201")]
    result = _audit(cp, window, bars)
    assert result["benchmark_outcome"]["status"] == "duplicate_session_bar"
    assert result["complete_portfolio_comparison"] is None


def test_provider_response_cannot_change_selected_symbols(tmp_path):
    cp, window = _mature(tmp_path)
    with pytest.raises(ForwardEvaluationError, match="outside"):
        _audit(cp, window, _prices(window) + [_bar("TSLA", window.entry_session, "100")])


def test_future_prices_cannot_enter_outcome_audit(tmp_path):
    cp, window = _mature(tmp_path)
    with pytest.raises(ForwardEvaluationError, match="after the frozen exit"):
        _audit(cp, window, _prices(window) + [_bar("MSFT", window.exit_session + timedelta(days=1), "105")])


def test_unexpected_invalid_core_reports_rejected(tmp_path):
    cp, window = _mature(tmp_path)
    with pytest.raises(ForwardEvaluationError, match="unexpected symbol"):
        _audit(cp, window, _prices(window), invalid_symbols={"TSLA"})


def test_zero_selection_creates_no_claim(tmp_path):
    cp, window = _mature(tmp_path, candidates=())
    result = _audit(cp, window, [_bar("SPY", window.entry_session, "200"), _bar("SPY", window.exit_session, "210")])
    assert result["status"] == "no_selection"
    assert result["complete_portfolio_comparison"] is None


@pytest.mark.parametrize("invalid", [Decimal(-1), Decimal(501), Decimal("NaN"), Decimal("Infinity")])
def test_invalid_execution_cost_rejected(invalid):
    with pytest.raises(ForwardEvaluationError, match="0–500"):
        validate_cost(invalid)


def test_cli_status_only_never_requests_historical_outcomes(tmp_path, monkeypatch, capsys):
    """Even a syntactically valid record has no realized outcome before exit."""
    from app.analysis import evaluate_forward_cli

    path, digest = _write_checkpoint(tmp_path)

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 11, 14, 23, tzinfo=UTC)

    def no_history(_settings):
        raise AssertionError("No outcome-price requests are allowed while pending")

    monkeypatch.setattr(evaluate_forward_cli, "datetime", FixedDateTime)
    monkeypatch.setattr(evaluate_forward_cli, "Settings", lambda: object())
    monkeypatch.setattr(evaluate_forward_cli, "get_market_calendar", lambda **_kwargs: {SIGNAL})
    monkeypatch.setattr(evaluate_forward_cli, "AlpacaHistoryClient", no_history)
    monkeypatch.setattr(
        "sys.argv", [
            "evaluate_forward_cli", "--record", str(path),
            "--expect-checksum", digest, "--status-only",
        ],
    )
    evaluate_forward_cli.main()
    assert "PENDING" in capsys.readouterr().out
    assert sorted(p.name for p in tmp_path.iterdir()) == ["forward.json"]


def test_cli_matured_evaluation_retrieves_only_to_exit_and_saves(tmp_path, monkeypatch, capsys):
    from app.analysis import evaluate_forward_cli

    path, digest = _write_checkpoint(tmp_path)
    out = tmp_path / "outcome.json"
    days, future = _calendar(21)
    cp = load_checkpoint(path, expected_checksum=digest)
    window = evaluation_window(cp, sessions=days, completed_through=future[-1])
    requests = []

    class FixedDateTime(datetime):
        @classmethod
        def now(cls, tz=None):
            return datetime(2026, 12, 31, 16, tzinfo=UTC)

    class FakeHistory:
        def __init__(self, _settings):
            pass

        def pages(self, symbols, *, start, end, feed, adjustment, page_limit, on_invalid_core):
            requests.append((symbols, start, end, feed, adjustment, page_limit))
            assert on_invalid_core is not None
            yield _prices(window)

    monkeypatch.setattr(evaluate_forward_cli, "datetime", FixedDateTime)
    monkeypatch.setattr(evaluate_forward_cli, "Settings", lambda: object())
    monkeypatch.setattr(evaluate_forward_cli, "get_market_calendar", lambda **_kwargs: days)
    monkeypatch.setattr(evaluate_forward_cli, "AlpacaHistoryClient", FakeHistory)
    monkeypatch.setattr(
        "sys.argv", [
            "evaluate_forward_cli", "--record", str(path),
            "--expect-checksum", digest, "--out", str(out),
        ],
    )
    evaluate_forward_cli.main()
    assert "Outcome status: complete" in capsys.readouterr().out
    assert len(requests) == 1
    symbols, start, end, feed, adjustment, limit = requests[0]
    assert symbols == ["AAPL", "MSFT", "SPY"]
    assert start == window.entry_session
    assert end.astimezone(ZoneInfo("America/New_York")).date() == window.exit_session
    assert (feed, adjustment, limit) == ("sip", "split", 10000)
    result = json.loads(out.read_text())
    assert result["source_checkpoint_sha256"] == digest
    assert result["status"] == "complete"
    assert result["content_sha256"]
    assert out.stat().st_mode & 0o777 == 0o600
