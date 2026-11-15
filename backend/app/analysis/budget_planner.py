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
InvestmentHorizon = Literal["short", "medium", "long"]
STYLES: dict[PlanStyle, tuple[int, int]] = {
    "cautious": (60, 0),
    "balanced": (65, 20),
    "growth": (70, 20),
}
# Deliberately conservative illustrations, not predicted risk/return or optimized weights.
# Short (within one year): do not put near-term funds into risky assets.
# Medium (one to five years): smaller illustrative risk exposure.
# Long (five-plus years): retains the previous 3E.1 illustrative styles.
HORIZON_STYLES: dict[InvestmentHorizon, dict[PlanStyle, tuple[int, int]]] = {
    "short": {
        "cautious": (0, 0), "balanced": (0, 0), "growth": (0, 0),
    },
    "medium": {
        "cautious": (25, 0), "balanced": (35, 10), "growth": (40, 10),
    },
    "long": STYLES,
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


def validate_max_loss(value: Decimal | None, budget: Decimal) -> Decimal | None:
    """Treat this as a *nominal-at-risk dollar cap*, not a loss forecast."""
    if value is None:
        return None
    if (
        not value.is_finite()
        or value < 0
        or value > budget
        or value * 100 != (value * 100).to_integral_value()
    ):
        raise BudgetPlanError("Affordable loss must be $0.00 through the budget, in whole cents")
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
    horizon: InvestmentHorizon = "long",
    max_loss_usd: Decimal | None = None,
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
    if horizon not in HORIZON_STYLES:
        raise BudgetPlanError("Unknown investment horizon")
    loss_cap = validate_max_loss(max_loss_usd, amount)
    if type(allow_experimental_stocks) is not bool:
        raise BudgetPlanError("Experimental opt-in must be a boolean")
    current = now or datetime.now(UTC)
    if current.utcoffset() is None:
        raise BudgetPlanError("Current time must be timezone-aware")
    core_pct, satellite_pct = HORIZON_STYLES[horizon][style]
    cents = int(amount * 100)
    allowed_risk_cents = cents if loss_cap is None else int(loss_cap * 100)
    desired_core_cents = cents * core_pct // 100
    desired_satellite_cents = cents * satellite_pct // 100
    # Core-first and *no leverage*: the full principal of risky assets is assumed
    # to be losable for this budgeting constraint, not just a forecasted drawdown.
    core_cents = min(desired_core_cents, allowed_risk_cents)
    satellite_cents = min(
        desired_satellite_cents, max(0, allowed_risk_cents - core_cents),
    )
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
    exposed_cents = core_cents + stock_spent
    if exposed_cents > allowed_risk_cents:
        raise BudgetPlanError("Risk exposure exceeds the affordable-loss cap")
    explanations = [
        {
            "short": "Within one year: this example leaves the budget in cash rather than putting near-term funds into stocks.",
            "medium": "One to five years: this example uses smaller illustrative equity slices to account for a shorter recovery window.",
            "long": "Five-plus years: this example uses the selected style's longer-horizon equity allocation; losses remain possible.",
        }[horizon],
    ]
    if loss_cap is None:
        explanations.append(
            "No maximum affordable loss supplied. This scenario has NOT applied a personal dollar-risk cap."
        )
    else:
        explanations.append(
            "Risky principal is limited to the stated affordable-loss amount, assuming no borrowing. "
            "This is an exposure cap, NOT a forecast or guarantee about market losses."
        )
    if allow_experimental_stocks and satellite_cents > 0 and not choices:
        explanations.append("No usable individual-stock ideas; their budget remains in cash.")
    elif not allow_experimental_stocks:
        explanations.append("Individual-stock ideas remain off until explicitly enabled.")
    # Hypothetical price falls apply to *all* risk-bearing dollars; cash is kept
    # at nominal value solely for this simple example, not guaranteed inflation safe.
    risk_usd = Decimal(exposed_cents) / 100
    stress_scenarios = [
        {
            "decline_percent": percent,
            "loss_usd": f"{risk_usd * Decimal(percent) / 100:.2f}",
            "remaining_budget_usd": f"{amount - risk_usd * Decimal(percent) / 100:.2f}",
        }
        for percent in (10, 30, 100)
    ]
    return {
        "budget_usd": f"{amount:.2f}",
        "style": style,
        "horizon": horizon,
        "max_loss_usd": f"{loss_cap:.2f}" if loss_cap is not None else None,
        "modeled_risky_principal_usd": f"{risk_usd:.2f}",
        "loss_cap_binding": loss_cap is not None and (
            core_cents < desired_core_cents
            or (bool(choices) and satellite_cents < desired_satellite_cents)
        ),
        "planning_explanations": explanations,
        "stress_scenarios": stress_scenarios,
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
            "Risk-dollar cap is a long-only exposure limit, not a calculated probability of loss or downside guarantee.",
            "Cash is modeled at nominal face value; inflation and other cash risks are excluded.",
            "Horizon percentages are illustrative policy examples, not tested or optimized portfolios.",
            "No brokerage orders are created.",
        ],
    }
