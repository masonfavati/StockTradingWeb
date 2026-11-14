"""Read-only, historical signal diagnostics for StockTradingWeb.

NOT a point-in-time market-wide backtest, a forecast, or executable P&L.
The input is *raw* completed-session bars from the local database. No
historical future bars are used when selecting candidate symbols. Entry is the
next session's opening price; exit is the opening price after `horizon`
additional sessions. Dividends, splits, delistings, taxes, financing, and
unobserved spreads are not modeled. A configurable cost is only a scenario.
"""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from app.analysis.opportunities import (
    MIN_SESSIONS,
    ResearchCandidate,
    describe_candidate,
    shortlist,
)
from app.market_data.history_client import DailyBar


@dataclass(frozen=True)
class SignalTrial:
    signal_date: date
    entry_date: date
    exit_date: date
    selected_symbols: tuple[str, ...]
    selected_net_return: Decimal
    tracked_universe_net_return: Decimal


@dataclass(frozen=True)
class SignalValidation:
    tracked_symbols: int
    recorded_sessions: int
    attempted_signals: int
    skipped_no_candidate: int
    skipped_incomplete_outcomes: int
    trials: tuple[SignalTrial, ...]
    horizon: int
    top_n: int
    cost_bps_per_side: Decimal

    @property
    def average_selected_return(self) -> Decimal | None:
        return _average([trial.selected_net_return for trial in self.trials])

    @property
    def average_universe_return(self) -> Decimal | None:
        return _average([trial.tracked_universe_net_return for trial in self.trials])

    @property
    def positive_selected_trials(self) -> int:
        return sum(trial.selected_net_return > 0 for trial in self.trials)

    @property
    def selected_beat_universe(self) -> int:
        return sum(
            trial.selected_net_return > trial.tracked_universe_net_return
            for trial in self.trials
        )


def _average(values: Sequence[Decimal]) -> Decimal | None:
    if not values:
        return None
    return sum(values, Decimal(0)) / Decimal(len(values))


def _net_return(entry: Decimal, exit_: Decimal, cost: Decimal) -> Decimal:
    # Explicit buy at next-session open, sell at a later-session open.
    # Cost is applied on *both* sides; not a measured spread or fill price.
    if not entry.is_finite() or not exit_.is_finite() or entry <= 0 or exit_ <= 0:
        raise ValueError("Invalid raw opening price")
    return exit_ * (Decimal(1) - cost) / (entry * (Decimal(1) + cost)) - Decimal(1)


def candidates_as_of(
    rows_by_symbol: Mapping[str, Sequence[DailyBar]],
    sessions: Sequence[date],
    signal_index: int,
) -> tuple[list[ResearchCandidate], list[str]]:
    """Use exactly the 61 previous/current market sessions, never future bars.

    Noncontiguous histories are not silently treated as an equally spaced
    61-session window. The broader *tracked* universe is used for comparison.
    """
    if signal_index < MIN_SESSIONS - 1 or signal_index >= len(sessions):
        raise ValueError("Signal index does not contain a complete history window")
    window = set(sessions[signal_index - MIN_SESSIONS + 1 : signal_index + 1])
    signal_day = sessions[signal_index]
    qualified: list[ResearchCandidate] = []
    observed: list[str] = []
    for symbol, bars in sorted(rows_by_symbol.items()):
        # Explicitly exclude all later bars before constructing any signal.
        prior = [row for row in bars if row.session_date <= signal_day]
        recent = [row for row in prior if row.session_date in window]
        if len(recent) != MIN_SESSIONS or {row.session_date for row in recent} != window:
            continue
        observed.append(symbol)
        candidate = describe_candidate(symbol, symbol, recent)
        if candidate is not None:
            qualified.append(candidate)
    return shortlist(qualified, limit=max(1, len(qualified))), observed


def validate_signals(
    rows: Sequence[DailyBar],
    *,
    horizon: int = 20,
    top_n: int = 1,
    cost_bps_per_side: Decimal = Decimal(10),
) -> SignalValidation:
    """Retrospectively audit an unchanged ranking rule using raw daily bars.

    Uses nonoverlapping signal windows by stepping `horizon` sessions. Signal
    timestamp is *after* the close; entry is no earlier than next open.
    Symbols are selected before inspecting future returns. If any selected
    symbol has no future prices, the trial is skipped (no favorable replacement).
    """
    if not 1 <= horizon <= 252:
        raise ValueError("Horizon must be 1 to 252 trading sessions")
    if not 1 <= top_n <= 20:
        raise ValueError("top_n must be 1 to 20")
    if (
        not cost_bps_per_side.is_finite()
        or not Decimal(0) <= cost_bps_per_side <= Decimal(500)
    ):
        raise ValueError("Cost must be from 0 to 500 basis points per side")
    cost = cost_bps_per_side / Decimal(10000)
    rows_by_symbol: dict[str, list[DailyBar]] = {}
    seen: set[tuple[str, date]] = set()
    for bar in rows:
        key = (bar.symbol, bar.session_date)
        if key in seen:
            raise ValueError("Duplicate raw bars in signal validation input")
        seen.add(key)
        rows_by_symbol.setdefault(bar.symbol, []).append(bar)
    for bars in rows_by_symbol.values():
        bars.sort(key=lambda row: row.session_date)
    sessions = sorted({bar.session_date for bar in rows})
    at_date = {
        symbol: {bar.session_date: bar for bar in bars}
        for symbol, bars in rows_by_symbol.items()
    }

    attempted = 0
    skipped_no_candidate = 0
    skipped_incomplete = 0
    trials: list[SignalTrial] = []
    # Exit is horizon sessions after the next-session opening. The last
    # (horizon + 1) sessions must be observable when auditing a decision.
    stop = len(sessions) - horizon - 1
    for index in range(MIN_SESSIONS - 1, stop, horizon):
        attempted += 1
        qualified, observed = candidates_as_of(rows_by_symbol, sessions, index)
        if not qualified or not observed:
            skipped_no_candidate += 1
            continue
        selected = tuple(item.symbol for item in qualified[:top_n])
        entry_day = sessions[index + 1]
        exit_day = sessions[index + 1 + horizon]
        # Never replace a previously selected stock if later data is absent.
        # A similarly complete comparison pool is required, to prevent the
        # baseline from cherry-picking surviving symbols after the fact.
        required = set(observed) | set(selected)
        if any(
            entry_day not in at_date[symbol]
            or exit_day not in at_date[symbol]
            for symbol in required
        ):
            skipped_incomplete += 1
            continue
        try:
            returns = {
                symbol: _net_return(
                    at_date[symbol][entry_day].open_price,
                    at_date[symbol][exit_day].open_price,
                    cost,
                )
                for symbol in required
            }
        except ValueError:
            skipped_incomplete += 1
            continue
        selected_mean = _average([returns[symbol] for symbol in selected])
        universe_mean = _average([returns[symbol] for symbol in observed])
        if selected_mean is None or universe_mean is None:
            raise ValueError("Insufficient prices for this signal comparison")
        trials.append(SignalTrial(
            signal_date=sessions[index],
            entry_date=entry_day,
            exit_date=exit_day,
            selected_symbols=selected,
            selected_net_return=selected_mean,
            tracked_universe_net_return=universe_mean,
        ))
    return SignalValidation(
        tracked_symbols=len(rows_by_symbol),
        recorded_sessions=len(sessions),
        attempted_signals=attempted,
        skipped_no_candidate=skipped_no_candidate,
        skipped_incomplete_outcomes=skipped_incomplete,
        trials=tuple(trials),
        horizon=horizon,
        top_n=top_n,
        cost_bps_per_side=cost_bps_per_side,
    )
