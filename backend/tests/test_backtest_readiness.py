"""Readiness reports must not substitute today's directory for a past universe."""

from datetime import date, timedelta

import pytest

from app.analysis.backtest_readiness import assess_readiness, snapshot_known_before_signal
from app.analysis.readiness_cli import print_report


def sessions(count: int) -> list[date]:
    result = []
    day = date(2026, 1, 5)
    while len(result) < count:
        if day.weekday() < 5:
            result.append(day)
        day += timedelta(days=1)
    return result


def report(count: int = 82, *, snapshot_date: date | None = None):
    dates = sessions(count)
    return assess_readiness(
        ["AAA", "BBB"],
        {"AAA": set(dates), "BBB": set(dates)},
        set(dates),
        snapshot_date=snapshot_date or date(2026, 11, 14),
    )


def test_future_snapshot_is_unusable_for_past_signal() -> None:
    assert not snapshot_known_before_signal(date(2026, 11, 14), date(2026, 11, 13))


def test_same_day_snapshot_is_not_assumed_known_at_decision_time() -> None:
    assert not snapshot_known_before_signal(date(2026, 11, 14), date(2026, 11, 14))


def test_earlier_snapshot_may_be_considered_known_but_not_verified() -> None:
    assert snapshot_known_before_signal(date(2025, 11, 14), date(2026, 11, 13))


def test_74_sessions_not_enough_for_61_plus_next_open_plus_20() -> None:
    result = report(74)
    assert result.required_sessions == 82
    assert result.full_lookback_symbols == 2
    assert result.complete_replay_symbols == 0
    assert result.earliest_replay_signal is None


def test_exact_82_sessions_provides_a_single_replay_date() -> None:
    result = report(82)
    assert result.complete_replay_symbols == 2
    assert result.earliest_replay_signal == sessions(82)[60]
    assert result.latest_replay_signal == sessions(82)[60]


def test_future_snapshot_blocks_replay_even_with_perfect_prices() -> None:
    result = report(103)
    assert result.complete_replay_symbols == 2
    assert result.point_in_time_replay_dates == 0
    assert result.can_validate_market_wide is False


def test_earlier_snapshot_makes_some_dates_eligible_for_examination() -> None:
    days = sessions(103)
    result = report(103, snapshot_date=days[60])
    assert result.point_in_time_replay_dates == 21
    assert result.can_validate_market_wide is False


def test_missing_one_lookback_day_flags_partial_history() -> None:
    days = sessions(82)
    result = assess_readiness(
        ["AAA"], {"AAA": set(days) - {days[60]}}, set(days),
        snapshot_date=date(2025, 1, 1),
    )
    assert result.symbols_with_data == 1
    assert result.complete_interval_symbols == 0
    assert result.full_lookback_symbols == 0  # last 61 includes day 60
    assert result.complete_replay_symbols == 0
    assert result.entries[0].missing_sessions == 1


def test_first_day_missing_is_not_silently_treated_as_complete() -> None:
    days = sessions(82)
    result = assess_readiness(
        ["AAA"], {"AAA": set(days[1:])}, set(days),
        snapshot_date=date(2025, 1, 1),
    )
    assert result.full_lookback_symbols == 1
    assert result.complete_replay_symbols == 0


def test_zero_price_history_is_reported_not_fabricated() -> None:
    days = sessions(82)
    result = assess_readiness(["AAA"], {}, set(days), snapshot_date=days[0])
    assert result.symbols_with_data == 0
    assert result.entries[0].first_recorded is None
    assert result.entries[0].last_recorded is None
    assert result.entries[0].recorded_sessions == 0


def test_pre_ipo_missing_dates_count_as_missing_coverage_not_corruption() -> None:
    days = sessions(82)
    result = assess_readiness(
        ["NEW"], {"NEW": set(days[40:])}, set(days), snapshot_date=days[0],
    )
    assert result.entries[0].missing_sessions == 40
    assert result.complete_replay_symbols == 0


def test_only_raw_dates_within_requested_calendar_are_counted() -> None:
    days = sessions(82)
    result = assess_readiness(
        ["AAA"], {"AAA": set(days) | {date(2025, 12, 1)}}, set(days),
        snapshot_date=days[0],
    )
    assert result.entries[0].recorded_sessions == 82
    assert result.entries[0].missing_sessions == 0


@pytest.mark.parametrize("horizon", [0, -1, 253])
def test_invalid_horizon_is_rejected(horizon: int) -> None:
    with pytest.raises(ValueError, match="Horizon"):
        assess_readiness(["AAA"], {}, set(sessions(4)), snapshot_date=date(2026, 1, 1), horizon=horizon)


def test_duplicate_symbols_cannot_fake_coverage() -> None:
    with pytest.raises(ValueError, match="unique"):
        assess_readiness(["AAA", "AAA"], {}, set(sessions(4)), snapshot_date=date(2026, 1, 1))


def test_exchange_calendar_is_required() -> None:
    with pytest.raises(ValueError, match="independent"):
        assess_readiness(["AAA"], {}, set(), snapshot_date=date(2026, 1, 1))


def test_unsolicited_symbol_is_rejected() -> None:
    with pytest.raises(ValueError, match="unrequested"):
        assess_readiness(["AAA"], {"BBB": set()}, set(sessions(4)), snapshot_date=date(2026, 1, 1))


def test_report_discloses_backtest_blocker(capsys: pytest.CaptureFixture[str]) -> None:
    result = report(82)
    print_report(result, profile="all", universe_total=1000, offset=0, fingerprint="example123")
    output = capsys.readouterr().out
    assert "BLOCKED" in output
    assert "61 lookback" in output
    assert "not validation of the entire market" in output
    assert "No profitability probability" in output


def test_two_symbols_are_counted_independently() -> None:
    days = sessions(82)
    result = assess_readiness(
        ["AAA", "BBB"], {"AAA": set(days), "BBB": set(days[:10])}, set(days),
        snapshot_date=date(2025, 1, 1),
    )
    assert result.symbols_with_data == 2
    assert result.complete_interval_symbols == 1
    assert result.full_lookback_symbols == 1
    assert result.complete_replay_symbols == 1


def test_unexpected_weekend_row_does_not_count_as_clean_history() -> None:
    days = sessions(82)
    extra = date(2026, 1, 10)  # Saturday within the requested calendar interval
    result = assess_readiness(
        ["AAA"], {"AAA": set(days) | {extra}}, set(days),
        snapshot_date=date(2025, 1, 1),
    )
    assert result.unexpected_date_symbols == 1
    assert result.complete_interval_symbols == 0
    assert result.full_lookback_symbols == 0
    assert result.complete_replay_symbols == 0
