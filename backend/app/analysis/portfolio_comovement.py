"""Bounded, retrospective co-movement diagnostics for an illustrative budget.

No predicted returns, future information, or verified issuer/sector claims. A
missing comparable price is never imputed. This is not an allocation optimizer.
"""

import math
import re
import statistics
from collections.abc import Iterator, Mapping, Sequence
from datetime import date, timedelta
from decimal import Decimal
from itertools import pairwise
from typing import Any, Protocol

from app.market_data.history_client import DailyBar, HistoryAdjustment, HistoryFeed

MIN_MATCHED_SESSIONS = 61  # 60 aligned daily returns
MAX_PAIRWISE_CORRELATION = 0.80
REFERENCE = "SPY"
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")


class HistoricalBars(Protocol):
    def pages(
        self, symbols: Sequence[str], *, start: date, end: date,
        feed: HistoryFeed, adjustment: HistoryAdjustment, page_limit: int,
    ) -> Iterator[list[DailyBar]]: ...


def _log_returns(prices: Sequence[float]) -> list[float]:
    return [math.log(current / previous) for previous, current in pairwise(prices)]


def _pearson(first: Sequence[float], second: Sequence[float]) -> float | None:
    if len(first) != len(second) or len(first) < 2:
        return None
    avg_a, avg_b = statistics.fmean(first), statistics.fmean(second)
    ca = [x - avg_a for x in first]
    cb = [y - avg_b for y in second]
    aa = math.fsum(x * x for x in ca)
    bb = math.fsum(y * y for y in cb)
    if aa <= 1e-22 or bb <= 1e-22:
        return None
    result = math.fsum(x * y for x, y in zip(ca, cb, strict=True)) / math.sqrt(aa * bb)
    return max(-1.0, min(1.0, result)) if math.isfinite(result) else None


def _empty_review(status: str, symbols: Sequence[str], *, reason: str) -> dict[str, Any]:
    return {
        "version": "adjusted-return-comovement-v1",
        "status": status,
        "requested_symbols": list(symbols),
        "approved_symbols": [],
        "excluded": [{"symbol": symbol, "reason": reason} for symbol in symbols],
        "matched_sessions": MIN_MATCHED_SESSIONS,
        "pairwise_correlations": [],
        "spy_correlations": [],
        "portfolio_annualized_historical_volatility_pct": None,
        "portfolio_historical_max_drawdown_pct": None,
        "threshold_positive_correlation": MAX_PAIRWISE_CORRELATION,
        "caveat": (
            "Retrospective adjusted daily-return comparisons, not verified security identities, "
            "industry diversification, predicted returns, or independently validated portfolio results."
        ),
    }


def analyze_historical_comovement(
    provider: HistoricalBars,
    *,
    signal_session: date,
    stock_amounts_usd: Mapping[str, Decimal],
    core_amount_usd: Decimal,
    budget_usd: Decimal,
) -> dict[str, Any]:
    """Fetch SPY and <=2 shortlisted names; fail closed on missing aligned evidence.

    This call is made ONLY after explicit user opt-in, via a bounded synchronous
    API operation. Does not persist prices or modify checkpoints.
    """
    symbols = list(stock_amounts_usd)
    if (
        len(symbols) > 2 or len(symbols) != len(set(symbols))
        or REFERENCE in symbols or any(_SYMBOL.fullmatch(s) is None for s in symbols)
        or not (Decimal(0) <= core_amount_usd <= budget_usd)
        or any(value <= 0 or value > budget_usd for value in stock_amounts_usd.values())
        or core_amount_usd + sum(stock_amounts_usd.values()) > budget_usd
    ):
        raise ValueError("Invalid bounded research symbols or budget weights")
    if not symbols:
        return _empty_review("not_applicable", [], reason="no_eligible_candidates")

    # End is exclusive and follows the *frozen* source session, not today.
    rows: dict[str, dict[date, float]] = {s: {} for s in [REFERENCE, *symbols]}
    for page in provider.pages(
        [REFERENCE, *symbols],
        start=signal_session - timedelta(days=130),
        end=signal_session + timedelta(days=1),
        feed="sip", adjustment="all", page_limit=1000,
    ):
        for bar in page:
            if bar.symbol not in rows:
                raise ValueError("Historical response contains an unrequested ticker")
            if bar.session_date > signal_session:
                raise ValueError("Historical response contains future session prices")
            price = float(bar.close_price)
            if not math.isfinite(price) or price <= 0 or bar.session_date in rows[bar.symbol]:
                raise ValueError("Historical prices contain invalid or duplicate sessions")
            rows[bar.symbol][bar.session_date] = price
    spy = rows[REFERENCE]
    dates = sorted(spy)
    if len(dates) < MIN_MATCHED_SESSIONS or dates[-1] != signal_session:
        return _empty_review("insufficient_history", symbols, reason="missing_spy_reference")
    aligned = dates[-MIN_MATCHED_SESSIONS:]
    spy_closes = [spy[d] for d in aligned]
    spy_returns = _log_returns(spy_closes)
    if _pearson(spy_returns, spy_returns) is None:
        return _empty_review("insufficient_history", symbols, reason="degenerate_reference_returns")

    approved: list[str] = []
    excluded: list[dict[str, str]] = []
    pairwise: list[dict[str, Any]] = []
    spy_correlations: list[dict[str, Any]] = []
    stock_prices: dict[str, list[float]] = {}
    stock_returns: dict[str, list[float]] = {}
    for symbol in symbols:
        observed = rows[symbol]
        if any(d not in observed for d in aligned):
            excluded.append({"symbol": symbol, "reason": "insufficient_aligned_sessions"})
            continue
        prices = [observed[d] for d in aligned]
        returns = _log_returns(prices)
        rel_spy = _pearson(returns, spy_returns)
        if rel_spy is None:
            excluded.append({"symbol": symbol, "reason": "degenerate_daily_returns"})
            continue
        spy_correlations.append({
            "symbol": symbol, "correlation": round(rel_spy, 3), "paired_returns": len(returns),
        })
        too_correlated = False
        for prior in approved:
            corr = _pearson(returns, stock_returns[prior])
            if corr is None:
                too_correlated = True
                excluded.append({"symbol": symbol, "reason": "unmeasurable_pair_correlation"})
                break
            pairwise.append({
                "symbol_a": prior, "symbol_b": symbol,
                "correlation": round(corr, 3), "paired_returns": len(returns),
            })
            if corr >= MAX_PAIRWISE_CORRELATION:
                excluded.append({"symbol": symbol, "reason": "high_positive_correlation"})
                too_correlated = True
                break
        if too_correlated:
            continue
        approved.append(symbol)
        stock_prices[symbol] = prices
        stock_returns[symbol] = returns

    # Retrospectively show a fixed-share, buy-and-hold scenario selected TODAY.
    # This is risk context only, with no strategy-performance interpretation.
    invested = core_amount_usd + sum(stock_amounts_usd[s] for s in approved)
    starting_cash = float(budget_usd - invested)
    balances = [
        starting_cash + float(core_amount_usd) * spy_closes[i] / spy_closes[0]
        + sum(
            float(stock_amounts_usd[s]) * stock_prices[s][i] / stock_prices[s][0]
            for s in approved
        )
        for i in range(len(aligned))
    ]
    vol: float | None = None
    drawdown: float | None = None
    if invested > 0 and min(balances) > 0:
        log_returns = _log_returns(balances)
        vol = round(statistics.stdev(log_returns) * math.sqrt(252) * 100, 2)
        high = balances[0]
        worst = 0.0
        for balance in balances:
            high = max(high, balance)
            worst = min(worst, balance / high - 1)
        drawdown = round(worst * 100, 2)
    return {
        "version": "adjusted-return-comovement-v1",
        "status": "checked",
        "requested_symbols": symbols,
        "approved_symbols": approved,
        "excluded": excluded,
        "matched_sessions": len(aligned),
        "pairwise_correlations": pairwise,
        "spy_correlations": spy_correlations,
        "portfolio_annualized_historical_volatility_pct": vol,
        "portfolio_historical_max_drawdown_pct": drawdown,
        "threshold_positive_correlation": MAX_PAIRWISE_CORRELATION,
        "caveat": (
            "Computed using split/dividend-adjusted daily closes through the saved scan date. "
            "Selection used hindsight; portfolio figures are a retrospective fixed-share illustration, "
            "not a forward backtest, investable portfolio, price quote, or loss bound. "
            "Industry and legal issuer identity are NOT verified."
        ),
    }


def unavailable_review(symbols: Sequence[str]) -> dict[str, Any]:
    """No partial provider results may be represented as approved evidence."""
    return _empty_review("unavailable", symbols, reason="historical_data_unavailable")
