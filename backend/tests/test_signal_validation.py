"""Walk-forward diagnostics must not leak future prices or fake trade fills."""

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from itertools import pairwise

import pytest

from app.analysis.signal_validation import candidates_as_of, validate_signals
from app.analysis.validation_cli import print_report
from app.market_data.history_client import DailyBar


def _sessions(count: int = 103) -> list[date]:
    result = []
    day = date(2025, 1, 2)
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day)
        day += timedelta(days=1)
    return result


def _bars(symbol: str, dates: list[date], *, steep: bool) -> list[DailyBar]:
    output = []
    for index, day in enumerate(dates):
        price = Decimal(100) + Decimal(index) * (Decimal("0.6") if steep else Decimal("0.12"))
        price += Decimal(index % 3) / 3
        output.append(DailyBar(
            symbol=symbol,
            session_date=day,
            bar_timestamp=datetime.combine(day, datetime.min.time(), tzinfo=UTC),
            open_price=price,
            high_price=price + 2,
            low_price=price - 2,
            close_price=price,
            volume=350000,
            trade_count=100,
            vwap=price,
        ))
    return output


def _dataset(count: int = 103) -> list[DailyBar]:
    days = _sessions(count)
    return _bars("AAA", days, steep=True) + _bars("BBB", days, steep=False)


def test_only_past_bars_used_to_rank_candidates() -> None:
    days = _sessions(82)
    first = _bars("AAA", days, steep=True)
    second = _bars("BBB", days, steep=False)
    initial, observed = candidates_as_of({"AAA": first, "BBB": second}, days, 60)
    assert observed == ["AAA", "BBB"]
    assert initial[0].symbol == "AAA"
    changed_second = second[:61] + [
        replace(row, open_price=Decimal(10000), high_price=Decimal(10001),
                low_price=Decimal(9999), close_price=Decimal(10000))
        for row in second[61:]
    ]
    after, _ = candidates_as_of({"AAA": first, "BBB": changed_second}, days, 60)
    assert initial == after


def test_entry_and_exit_use_later_open_not_signal_close() -> None:
    days = _sessions(82)
    first = _bars("AAA", days, steep=True)
    second = _bars("BBB", days, steep=False)
    first[61] = replace(first[61], open_price=Decimal(200))
    first[81] = replace(first[81], open_price=Decimal(220))
    result = validate_signals(first + second, horizon=20, cost_bps_per_side=Decimal(0))
    assert len(result.trials) == 1
    trial = result.trials[0]
    assert trial.selected_symbols == ("AAA",)
    assert (trial.signal_date, trial.entry_date, trial.exit_date) == (days[60], days[61], days[81])
    assert trial.selected_net_return == Decimal("0.1")


def test_costs_applied_to_both_sides() -> None:
    data = _dataset(82)
    without = validate_signals(data, horizon=20, cost_bps_per_side=Decimal(0))
    with_cost = validate_signals(data, horizon=20, cost_bps_per_side=Decimal(10))
    assert len(with_cost.trials) == len(without.trials) == 1
    gross = without.trials[0].selected_net_return
    expected = (gross + 1) * Decimal("0.999") / Decimal("1.001") - 1
    assert with_cost.trials[0].selected_net_return == expected
    assert with_cost.trials[0].selected_net_return < gross


def test_missing_winner_outcome_is_not_replaced_by_next_ranked_stock() -> None:
    data = [row for row in _dataset(82) if not (row.symbol == "AAA" and row.session_date == _sessions(82)[81])]
    result = validate_signals(data, horizon=20)
    assert result.attempted_signals == 1
    assert result.skipped_incomplete_outcomes == 1
    assert not result.trials


def test_missing_history_does_not_create_false_61_session_window() -> None:
    days = _sessions(82)
    first = _bars("AAA", days, steep=True)
    second = [row for row in _bars("BBB", days, steep=False) if row.session_date != days[32]]
    _, observed = candidates_as_of({"AAA": first, "BBB": second}, days, 60)
    assert observed == ["AAA"]


def test_signal_windows_do_not_overlap_at_horizon_20() -> None:
    result = validate_signals(_dataset(125), horizon=20)
    assert len(result.trials) >= 2
    for previous, current in pairwise(result.trials):
        assert previous.exit_date <= current.entry_date


def test_duplicate_dates_are_rejected() -> None:
    data = _dataset(82)
    with pytest.raises(ValueError, match="Duplicate"):
        validate_signals([*data, data[0]])


def test_invalid_parameters_are_rejected() -> None:
    data = _dataset(82)
    with pytest.raises(ValueError, match="Horizon"):
        validate_signals(data, horizon=0)
    with pytest.raises(ValueError, match="top_n"):
        validate_signals(data, top_n=0)
    with pytest.raises(ValueError, match="Cost"):
        validate_signals(data, cost_bps_per_side=Decimal("NaN"))
    with pytest.raises(ValueError, match="Cost"):
        validate_signals(data, cost_bps_per_side=Decimal(-1))


def test_too_few_sessions_produces_no_fake_results() -> None:
    result = validate_signals(_dataset(65), horizon=20)
    assert result.attempted_signals == 0
    assert result.average_selected_return is None
    assert result.average_universe_return is None
    assert result.positive_selected_trials == 0


def test_report_keeps_critical_limitations_visible(capsys: pytest.CaptureFixture[str]) -> None:
    report = validate_signals(_dataset(82), horizon=20)
    print_report(report)
    output = capsys.readouterr().out
    assert "INSUFFICIENT EVIDENCE" in output
    assert "only stocks already saved locally" in output
    assert "No actual trades" in output
    assert "raw" in output.lower()
