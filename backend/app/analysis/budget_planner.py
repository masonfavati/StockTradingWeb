"""Cents-exact, illustrative budget scenarios; NOT personalized buy advice.

Core ETF is an illustrative ticker, not a verified recommendation or live quote.
Satellite ideas are never used without an explicit opt-in and a fresh full scan.
"""

import math
import re
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.market_data.security_profiles import classify_security

PlanStyle = Literal["cautious", "balanced", "growth"]
STYLES: dict[PlanStyle, tuple[int, int]] = {
    "cautious": (60, 0),
    "balanced": (65, 20),
    "growth": (70, 20),
}
MAX_SINGLE_STOCK_PCT = 10
MAX_SCAN_AGE = timedelta(hours=96)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")
NY = ZoneInfo("America/New_York")


class BudgetPlanError(ValueError):
    """Request exceeds the supported planning bounds."""


def validate_budget(value: Decimal) -> Decimal:
    if (
        not value.is_finite()
        or value <= 0
        or value > Decimal(1_000_000)
        or value * 100 != (value * 100).to_integral_value()
    ):
        raise BudgetPlanError("Budget must be $0.01–$1,000,000.00 in whole cents")
    return value.quantize(Decimal("0.01"))


def _eligible_ideas(
    candidates: Sequence[Mapping[str, Any]], latest_session: str | None,
) -> list[dict[str, Any]]:
    """Heuristic common-share evidence is still NOT authoritative type verification."""
    picked: list[dict[str, Any]] = []
    seen: set[str] = set()
    for raw in candidates:
        symbol = raw.get("symbol")
        name = raw.get("name")
        historical_close = raw.get("adjusted_close")
        if (
            not isinstance(symbol, str)
            or not isinstance(name, str)
            or _SYMBOL.fullmatch(symbol) is None
            or symbol in seen
            or raw.get("last_session") != latest_session
            or classify_security(symbol, name) != "common_name_evidence"
            or isinstance(historical_close, bool)
            or not isinstance(historical_close, (float, int))
            or not math.isfinite(historical_close)
            or historical_close <= 0
        ):
            continue
        seen.add(symbol)
        picked.append({
            "symbol": symbol,
            "name": name,
            "historical_adjusted_close": str(historical_close),
        })
        if len(picked) == 2:
            break
    return picked


def make_budget_plan(
    budget: Decimal,
    style: PlanStyle,
    *,
    allow_experimental_stocks: bool,
    scan_state: str,
    scan_completed_at: str | None,
    scan_latest_session: str | None,
    candidates: Sequence[Mapping[str, Any]],
    now: datetime | None = None,
) -> dict[str, Any]:
    """Return illustrative dollar slices, with remaining pennies assigned to cash."""
    amount = validate_budget(budget)
    if style not in STYLES:
        raise BudgetPlanError("Unknown planning style")
    if type(allow_experimental_stocks) is not bool:
        raise BudgetPlanError("Experimental opt-in must be a boolean")
    current = now or datetime.now(UTC)
    if current.utcoffset() is None:
        raise BudgetPlanError("Current time must be timezone-aware")
    core_pct, satellite_pct = STYLES[style]
    cents = int(amount * 100)
    core_cents = cents * core_pct // 100
    satellite_cents = cents * satellite_pct // 100
    recent = False
    if scan_state == "complete" and scan_completed_at and scan_latest_session:
        try:
            scan_time = datetime.fromisoformat(scan_completed_at)
            age = current - scan_time
            session_day = date.fromisoformat(scan_latest_session)
            calendar_age = (current.astimezone(NY).date() - session_day).days
            recent = (
                scan_time.utcoffset() is not None
                and timedelta(0) <= age <= MAX_SCAN_AGE
                and 0 <= calendar_age <= 5
            )
        except (ValueError, TypeError):
            recent = False
    choices = (
        _eligible_ideas(candidates, scan_latest_session)
        if allow_experimental_stocks and recent and satellite_cents >= 2
        else []
    )
    allocations: list[dict[str, Any]] = [
        {
            "category": "diversified_core_example",
            "symbol": "SPY",
            "name": "Broad U.S. market ETF example (SPY)",
            "amount_usd": f"{Decimal(core_cents) / 100:.2f}",
            "percent_of_budget": round(100 * core_cents / cents, 2),
            "indicative_fractional_shares": None,
            "historical_price_usd": None,
            "reason": "Illustrates a diversified core rather than a single-company bet."
        }
    ]
    stock_spent = 0
    if choices:
        per_stock_limit = cents * MAX_SINGLE_STOCK_PCT // 100
        per_stock = min(per_stock_limit, satellite_cents // len(choices))
        for candidate in choices:
            if per_stock < 1:
                break
            stock_spent += per_stock
            price = Decimal(candidate["historical_adjusted_close"])
            estimate = (Decimal(per_stock) / 100 / price).quantize(
                Decimal("0.0001"), rounding=ROUND_DOWN,
            )
            allocations.append({
                "category": "experimental_stock_idea",
                "symbol": candidate["symbol"],
                "name": candidate["name"],
                "amount_usd": f"{Decimal(per_stock) / 100:.2f}",
                "percent_of_budget": round(100 * per_stock / cents, 2),
                "indicative_fractional_shares": str(estimate),
                "historical_price_usd": candidate["historical_adjusted_close"],
                "reason": "Unvalidated momentum/volatility screen; optional research idea only.",
            })
    cash_cents = cents - core_cents - stock_spent
    allocations.append({
        "category": "cash",
        "symbol": None,
        "name": "Cash / unallocated budget",
        "amount_usd": f"{Decimal(cash_cents) / 100:.2f}",
        "percent_of_budget": round(100 * cash_cents / cents, 2),
        "indicative_fractional_shares": None,
        "historical_price_usd": None,
        "reason": "Unallocated portion, including any experimental slice that lacks reliable candidates.",
    })
    if sum(Decimal(row["amount_usd"]) for row in allocations) != amount:
        raise BudgetPlanError("Allocation ledger does not reconcile")
    return {
        "budget_usd": f"{amount:.2f}",
        "style": style,
        "experimental_opt_in": allow_experimental_stocks,
        "scan_usable_for_ideas": recent,
        "source_session": scan_latest_session if recent else None,
        "allocation": allocations,
        "total_invested_example_usd": f"{Decimal(core_cents + stock_spent) / 100:.2f}",
        "unallocated_cash_usd": f"{Decimal(cash_cents) / 100:.2f}",
        "illustrative_equity_drop_30pct_usd": f"{Decimal(core_cents + stock_spent) * Decimal('0.30') / 100:.2f}",
        "warnings": [
            "This is a budget scenario, not advice about what you personally should buy.",
            "SPY is an example diversified ETF, not a price-checked or personalized recommendation.",
            "Individual stock ideas use name-based screening, not verified security classifications or validated return forecasts.",
            "Fractional shares use past adjusted closes, NOT executable quotes. Actual shares, orders, fees and fractional-trading support may differ.",
            "A 30% market drop is a stress example, not the worst possible loss or a forecast.",
            "No brokerage orders are created.",
        ],
    }
