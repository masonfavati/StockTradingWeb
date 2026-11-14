"""Exploratory completed-day statistics, NOT a validated return forecast.

The current `all` adjustment is suitable for descriptive as-of-now screening.
Never use it as time-travel-safe training data without point-in-time controls.
"""

import math
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date
from itertools import pairwise

from app.market_data.history_client import DailyBar

# These are transparent *screening thresholds*, not optimized trading rules.
MIN_SESSIONS = 61
MIN_ADJUSTED_CLOSE = 2.0
MIN_APPROX_DOLLAR_VOLUME = 1_000_000.0
MAX_ANNUALIZED_VOLATILITY = 1.2


@dataclass(frozen=True)
class ResearchCandidate:
    symbol: str
    name: str
    last_session: date
    adjusted_close: float
    return_20d_pct: float
    return_60d_pct: float
    annualized_volatility_pct: float
    drawdown_60d_pct: float
    approx_daily_dollar_volume: float
    research_score: float


def describe_candidate(
    symbol: str,
    name: str,
    bars: Sequence[DailyBar],
) -> ResearchCandidate | None:
    """Calculate comparable metrics from completed, adjusted daily candles.

    No stock price is predicted; the score is a *descriptive* 60-day
    performance/volatility ratio. The output is not a profit probability.
    """
    ordered = sorted(bars, key=lambda item: item.session_date)
    if len(ordered) < MIN_SESSIONS:
        return None
    dates = [bar.session_date for bar in ordered]
    if len(set(dates)) != len(dates):
        # Ambiguous duplicate sessions invalidate the candidate.
        return None

    recent = ordered[-MIN_SESSIONS:]
    closes = [float(bar.close_price) for bar in recent]
    if any(not math.isfinite(price) or price <= 0 for price in closes):
        return None
    last = closes[-1]
    if last < MIN_ADJUSTED_CLOSE:
        return None

    returns = [math.log(current / previous) for previous, current in pairwise(closes)]
    volatility = statistics.stdev(returns) * math.sqrt(252)
    if not math.isfinite(volatility) or volatility <= 0 or volatility > MAX_ANNUALIZED_VOLATILITY:
        return None

    volume = statistics.mean(float(bar.close_price) * bar.volume for bar in recent[-20:])
    if not math.isfinite(volume) or volume < MIN_APPROX_DOLLAR_VOLUME:
        return None
    r20 = last / closes[-21] - 1
    r60 = last / closes[0] - 1
    # Positive 60-session price momentum is a candidate SCREEN, not a prediction.
    if r60 <= 0:
        return None
    peak = max(closes)
    drawdown = last / peak - 1
    score = r60 / volatility
    if not math.isfinite(score):
        return None
    return ResearchCandidate(
        symbol=symbol,
        name=name,
        last_session=recent[-1].session_date,
        adjusted_close=round(last, 4),
        return_20d_pct=round(r20 * 100, 2),
        return_60d_pct=round(r60 * 100, 2),
        annualized_volatility_pct=round(volatility * 100, 2),
        drawdown_60d_pct=round(drawdown * 100, 2),
        approx_daily_dollar_volume=round(volume, 0),
        research_score=round(score, 4),
    )


def shortlist(candidates: Sequence[ResearchCandidate], *, limit: int = 20) -> list[ResearchCandidate]:
    """Descending descriptive score; stable symbol tie-breaker."""
    if limit < 1:
        raise ValueError("limit must be positive")
    return sorted(candidates, key=lambda row: (-row.research_score, row.symbol))[:limit]
