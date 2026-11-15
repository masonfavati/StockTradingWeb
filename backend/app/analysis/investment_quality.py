"""Explainable, conservative *research* gates for optional stock budget slices.

Metrics are historical descriptive scanner outputs, not broker-verified security
identities, executable liquidity, expected returns, or investment advice.
This module intentionally makes no network requests and never modifies a scan.
"""

import math
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from typing import Any

from app.market_data.security_profiles import classify_security

MIN_PRICE_USD = 5.0
MIN_APPROX_DAILY_DOLLAR_VOLUME_USD = 5_000_000.0
MAX_ANNUALIZED_VOLATILITY_PCT = 80.0
MIN_60D_DRAWDOWN_PCT = -25.0
MAX_SATELLITES = 2
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")
_CLASS_AND_COMMON = re.compile(
    r"\b(?:class\s+[a-z0-9-]+\s+)?(?:common\s+(?:stock|shares?)|ordinary\s+shares?)\b",
    flags=re.IGNORECASE,
)
_SPACES = re.compile(r"[^a-z0-9]+", flags=re.IGNORECASE)


def _number(row: Mapping[str, Any], key: str) -> float | None:
    raw = row.get(key)
    if isinstance(raw, bool) or not isinstance(raw, (int, float)):
        return None
    try:
        number = float(raw)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _issuer_name_key(name: str) -> str:
    """Name-only approximation for multiple share classes; NOT legal entity ID."""
    stripped = _CLASS_AND_COMMON.sub("", name)
    return _SPACES.sub("", stripped).lower()


def screen_budget_candidates(
    candidates: Sequence[Mapping[str, Any]],
    session: str | None,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Preserve ranked order while gating up to two distinct apparent issuers.

    A missing input or unverified security classification fails closed. We never
    infer a missing risk/liquidity value, and never label survivors 'safe'.
    """
    selected: list[dict[str, Any]] = []
    counts: Counter[str] = Counter()
    seen_symbols: set[str] = set()
    seen_issuers: set[str] = set()
    examined = 0
    for row in candidates:
        examined += 1
        symbol, name = row.get("symbol"), row.get("name")
        if (
            not isinstance(symbol, str)
            or _SYMBOL.fullmatch(symbol) is None
            or not isinstance(name, str)
            or not name.strip()
            or classify_security(symbol, name) != "common_name_evidence"
        ):
            counts["unverified_share_type"] += 1
            continue
        if symbol in seen_symbols:
            counts["duplicate_ticker"] += 1
            continue
        seen_symbols.add(symbol)
        if session is None or row.get("last_session") != session:
            counts["outdated_session"] += 1
            continue
        price = _number(row, "adjusted_close")
        vol = _number(row, "annualized_volatility_pct")
        drawdown = _number(row, "drawdown_60d_pct")
        liquidity = _number(row, "approx_daily_dollar_volume")
        if any(value is None for value in (price, vol, drawdown, liquidity)):
            counts["missing_or_invalid_metrics"] += 1
            continue
        assert price is not None and vol is not None
        assert drawdown is not None and liquidity is not None
        if price < MIN_PRICE_USD:
            counts["below_price_floor"] += 1
            continue
        if liquidity < MIN_APPROX_DAILY_DOLLAR_VOLUME_USD:
            counts["below_liquidity_screen"] += 1
            continue
        if vol <= 0 or vol > MAX_ANNUALIZED_VOLATILITY_PCT:
            counts["above_volatility_screen"] += 1
            continue
        if drawdown > 0 or drawdown < MIN_60D_DRAWDOWN_PCT:
            counts["outside_drawdown_screen"] += 1
            continue
        issuer = _issuer_name_key(name)
        if not issuer or issuer in seen_issuers:
            counts["repeated_apparent_issuer"] += 1
            continue
        seen_issuers.add(issuer)
        if len(selected) >= MAX_SATELLITES:
            counts["passed_not_selected"] += 1
            continue
        selected.append({
            "symbol": symbol,
            "name": name,
            "historical_adjusted_close": f"{price:g}",
            "annualized_volatility_pct": vol,
            "drawdown_60d_pct": drawdown,
            "approx_daily_dollar_volume": round(liquidity),
        })
    return selected, {
        "version": "descriptive-quality-screen-v1",
        "screened_count": examined,
        "selected_count": len(selected),
        "excluded_counts": dict(sorted(counts.items())),
        "thresholds": {
            "min_adjusted_close_usd": MIN_PRICE_USD,
            "min_approx_daily_dollar_volume_usd": MIN_APPROX_DAILY_DOLLAR_VOLUME_USD,
            "max_annualized_volatility_pct": MAX_ANNUALIZED_VOLATILITY_PCT,
            "min_60d_drawdown_pct": MIN_60D_DRAWDOWN_PCT,
            "max_individual_stocks": MAX_SATELLITES,
        },
        "caveat": (
            "Heuristic share names and adjusted historical trading metrics only. "
            "No verified company identity, live liquidity, industry correlation, "
            "predicted returns, or guarantee of safety."
        ),
    }
