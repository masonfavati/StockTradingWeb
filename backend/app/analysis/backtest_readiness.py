"""Read-only coverage diagnostics for historical, market-wide stock research.

A snapshot captured today does not establish historical membership yesterday.
Passing this audit is NOT a validated backtest or investment recommendation.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date

from app.analysis.opportunities import MIN_SESSIONS


@dataclass(frozen=True)
class SymbolCoverage:
    symbol: str
    recorded_sessions: int
    missing_sessions: int
    unexpected_sessions: int
    first_recorded: date | None
    last_recorded: date | None
    has_full_lookback: bool
    has_complete_replay_window: bool


@dataclass(frozen=True)
class ReadinessReport:
    snapshot_date: date
    start: date
    end: date
    trading_sessions: int
    selected_symbols: int
    symbols_with_data: int
    complete_interval_symbols: int
    unexpected_date_symbols: int
    full_lookback_symbols: int
    complete_replay_symbols: int
    earliest_replay_signal: date | None
    latest_replay_signal: date | None
    point_in_time_replay_dates: int
    horizon: int
    entries: tuple[SymbolCoverage, ...]

    @property
    def required_sessions(self) -> int:
        # 61 history sessions, followed by next-open entry and later exit.
        return MIN_SESSIONS + 1 + self.horizon

    @property
    def can_validate_market_wide(self) -> bool:
        # This audit can NEVER independently certify market-wide validity:
        # historical price revisions, delistings and security identity remain.
        return False


def snapshot_known_before_signal(snapshot_date: date, signal_date: date) -> bool:
    """Conservative date-only gate: same-day observations lack decision-time proof.

    Must be replaced with timestamp-level historical status records before
    intraday or same-day decision simulation can be allowed.
    """
    return snapshot_date < signal_date


def assess_readiness(
    symbols: Sequence[str],
    raw_dates: Mapping[str, set[date]],
    expected_sessions: set[date],
    *,
    snapshot_date: date,
    horizon: int = 20,
) -> ReadinessReport:
    """Check exact exchange-session coverage, without guessing missing IPO dates.

    The union of observed prices must NOT substitute for exchange sessions.
    Counts describe data sufficiency only; historical universe validity is
    separately gated by the real date on which the snapshot was observed.
    """
    if not 1 <= horizon <= 252:
        raise ValueError("Horizon must be 1 to 252 sessions")
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Choose a nonempty unique symbol sample")
    if not expected_sessions:
        raise ValueError("An independent exchange calendar is required")
    ordered = sorted(expected_sessions)
    if any(day.weekday() >= 5 for day in ordered):
        raise ValueError("Exchange calendar unexpectedly includes a weekend")
    if any(symbol not in symbols for symbol in raw_dates):
        raise ValueError("Records for unrequested symbols cannot be audited")
    first, last = ordered[0], ordered[-1]
    lookback = set(ordered[-MIN_SESSIONS:]) if len(ordered) >= MIN_SESSIONS else None
    # Each complete historical replay needs 61 trading sessions through its
    # signal, then an entry next session and an exit horizon sessions later.
    replay_windows = [
        (ordered[index], set(ordered[index - MIN_SESSIONS + 1 : index + horizon + 2]))
        for index in range(MIN_SESSIONS - 1, len(ordered) - horizon - 1)
    ]
    past_signals = [day for day, _ in replay_windows]
    valid_pit_dates = sum(snapshot_known_before_signal(snapshot_date, day) for day in past_signals)

    result: list[SymbolCoverage] = []
    for symbol in symbols:
        observed = raw_dates.get(symbol, set())
        if any(not isinstance(day, date) for day in observed):
            raise ValueError(f"Invalid observed date for {symbol}")
        window_observed = {day for day in observed if first <= day <= last}
        in_range = window_observed & expected_sessions
        unexpected = len(window_observed - expected_sessions)
        sorted_days = sorted(in_range)
        result.append(SymbolCoverage(
            symbol=symbol,
            recorded_sessions=len(in_range),
            missing_sessions=len(expected_sessions - in_range),
            unexpected_sessions=unexpected,
            first_recorded=sorted_days[0] if sorted_days else None,
            last_recorded=sorted_days[-1] if sorted_days else None,
            has_full_lookback=(unexpected == 0 and lookback is not None and lookback <= in_range),
            has_complete_replay_window=(unexpected == 0 and any(window <= in_range for _, window in replay_windows)),
        ))
    return ReadinessReport(
        snapshot_date=snapshot_date,
        start=first,
        end=last,
        trading_sessions=len(ordered),
        selected_symbols=len(symbols),
        symbols_with_data=sum(row.recorded_sessions > 0 for row in result),
        complete_interval_symbols=sum(row.missing_sessions == 0 and row.unexpected_sessions == 0 for row in result),
        unexpected_date_symbols=sum(row.unexpected_sessions > 0 for row in result),
        full_lookback_symbols=sum(row.has_full_lookback for row in result),
        complete_replay_symbols=sum(row.has_complete_replay_window for row in result),
        earliest_replay_signal=past_signals[0] if past_signals else None,
        latest_replay_signal=past_signals[-1] if past_signals else None,
        point_in_time_replay_dates=valid_pit_dates,
        horizon=horizon,
        entries=tuple(result),
    )
