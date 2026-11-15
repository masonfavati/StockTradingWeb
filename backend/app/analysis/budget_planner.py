"""Cents-exact, illustrative budget scenarios; NOT personalized buy advice.

Core ETF is an illustrative ticker, not a verified recommendation or live quote.
Satellite ideas are never used without an explicit opt-in and a fresh full scan.
"""

from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_DOWN, Decimal
from typing import Any, Literal
from zoneinfo import ZoneInfo

from app.analysis.investment_quality import screen_budget_candidates

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
    require_historical_comovement: bool = False,
    comovement_review: Mapping[str, Any] | None = None,
    require_sec_identity: bool = False,
    sec_identity_review: Mapping[str, Any] | None = None,
    require_sec_industry: bool = False,
    sec_industry_review: Mapping[str, Any] | None = None,
    require_prediction: bool = False,
    prediction_review: Mapping[str, Any] | None = None,
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
    if type(require_historical_comovement) is not bool:
        raise BudgetPlanError("Co-movement opt-in must be a boolean")
    if type(require_sec_identity) is not bool:
        raise BudgetPlanError("SEC identity opt-in must be a boolean")
    if type(require_sec_industry) is not bool:
        raise BudgetPlanError("SEC SIC opt-in must be a boolean")
    if type(require_prediction) is not bool:
        raise BudgetPlanError("Prediction-evidence opt-in must be a boolean")
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
    # Every individual-stock allocation is conditional on these independent
    # historical quality screens; absent data is NEVER guessed or accepted.
    checked = allow_experimental_stocks and recent and satellite_cents >= 2
    choices, quality_review = screen_budget_candidates(
        candidates if checked else [], scan_latest_session if checked else None,
    )
    quality_review["applied"] = checked
    if require_sec_identity and allow_experimental_stocks:
        # An absent/malformed SEC reference cannot authorize experimental stock
        # dollars. The original two-stock allocation slots remain reserved.
        approved_sec: set[str] = set()
        if sec_identity_review is not None and sec_identity_review.get("status") == "checked":
            verified = sec_identity_review.get("approved_symbols")
            if isinstance(verified, list) and all(isinstance(s, str) for s in verified):
                approved_sec = set(verified)
        before = len(choices)
        choices = [row for row in choices if row["symbol"] in approved_sec]
        quality_review["selected_count"] = len(choices)
        quality_review["sec_gated_count"] = before - len(choices)
    if require_sec_industry and allow_experimental_stocks:
        # Filer SIC evidence is additive and must not authorize a stock that the
        # existing quality and optional SEC-filer checks already rejected.
        approved_industry: set[str] = set()
        if sec_industry_review is not None and sec_industry_review.get("status") == "checked":
            verified = sec_industry_review.get("approved_symbols")
            if isinstance(verified, list) and all(isinstance(row, str) for row in verified):
                approved_industry = set(verified)
        prior = len(choices)
        choices = [row for row in choices if row["symbol"] in approved_industry]
        quality_review["selected_count"] = len(choices)
        quality_review["industry_gated_count"] = prior - len(choices)
    if require_prediction and allow_experimental_stocks:
        approved_prediction: set[str] = set()
        if prediction_review is not None and prediction_review.get("status") == "research_gate_passed":
            verified = prediction_review.get("approved_symbols")
            if isinstance(verified, list) and all(isinstance(symbol, str) for symbol in verified):
                approved_prediction = set(verified)
        before = len(choices)
        choices = [row for row in choices if row["symbol"] in approved_prediction]
        quality_review["selected_count"] = len(choices)
        quality_review["prediction_gated_count"] = before - len(choices)
    if require_historical_comovement and allow_experimental_stocks:
        # Only *server-supplied* aligned evidence may authorize stock dollars.
        # If the comparison cannot be performed, all experimental dollars stay cash.
        approved = set()
        if comovement_review is not None and comovement_review.get("status") == "checked":
            reviewed = comovement_review.get("approved_symbols")
            if isinstance(reviewed, list) and all(isinstance(s, str) for s in reviewed):
                approved = set(reviewed)
        initially_eligible = len(choices)
        choices = [row for row in choices if row["symbol"] in approved]
        quality_review["selected_count"] = len(choices)
        quality_review["correlation_gated_count"] = initially_eligible - len(choices)
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
        # An evidence-rejected stock's slice stays as cash. Never increase the
        # survivors' weights after the historical portfolio review was computed.
        denominator = len(choices)
        if require_sec_identity and sec_identity_review is not None:
            proposed = sec_identity_review.get("requested_symbols")
            if isinstance(proposed, list) and 1 <= len(proposed) <= 2:
                denominator = max(denominator, len(proposed))
        if require_sec_industry and sec_industry_review is not None:
            requested = sec_industry_review.get("requested_symbols")
            if isinstance(requested, list) and 1 <= len(requested) <= 2:
                denominator = max(denominator, len(requested))
        if require_prediction and prediction_review is not None:
            slots = prediction_review.get("proposed_slot_count")
            if type(slots) is int and 1 <= slots <= 2:
                denominator = max(denominator, slots)
        if require_historical_comovement and comovement_review is not None:
            requested = comovement_review.get("requested_symbols")
            if isinstance(requested, list) and 1 <= len(requested) <= 2:
                denominator = max(denominator, len(requested))
        per_stock = min(per_stock_limit, satellite_cents // denominator)
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
                "reason": (
                    "Optional, unvalidated research idea; historical 20-session approximate "
                    "dollar volume ${:,.0f}, annualized volatility {:.1f}%, "
                    "60-session drawdown {:.1f}%. No sector/correlation proof."
                ).format(
                    candidate["approx_daily_dollar_volume"],
                    candidate["annualized_volatility_pct"],
                    candidate["drawdown_60d_pct"],
                ),
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
        explanations.append(
            "No currently eligible individual-stock ideas with the requested evidence; "
            "the optional slice remains cash instead of being forced into a ticker."
        )
    elif allow_experimental_stocks and choices:
        explanations.append(
            "Optional stock ideas passed conservative historical price, approximate "
            "dollar-volume, volatility and drawdown screens; this does NOT show "
            "that returns are predictable or correlations will stay constant."
        )
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
        "quality_review": quality_review,
        "historical_comovement_required": require_historical_comovement and allow_experimental_stocks,
        "comovement_review": dict(comovement_review) if require_historical_comovement and comovement_review is not None else None,
        "sec_identity_required": require_sec_identity and allow_experimental_stocks,
        "sec_identity_review": dict(sec_identity_review) if require_sec_identity and allow_experimental_stocks and sec_identity_review is not None else None,
        "sec_industry_required": require_sec_industry and allow_experimental_stocks,
        "sec_industry_review": dict(sec_industry_review) if require_sec_industry and allow_experimental_stocks and sec_industry_review is not None else None,
        "prediction_required": require_prediction and allow_experimental_stocks,
        "prediction_review": dict(prediction_review) if require_prediction and allow_experimental_stocks and prediction_review is not None else None,
        "scan_usable_for_ideas": recent,
        "source_session": scan_latest_session if recent else None,
        "allocation": allocations,
        "total_invested_example_usd": f"{Decimal(core_cents + stock_spent) / 100:.2f}",
        "unallocated_cash_usd": f"{Decimal(cash_cents) / 100:.2f}",
        "illustrative_equity_drop_30pct_usd": f"{Decimal(core_cents + stock_spent) * Decimal('0.30') / 100:.2f}",
        "warnings": [
            "This is a budget scenario, not advice about what you personally should buy.",
            "SPY is an example diversified ETF, not a price-checked or personalized recommendation.",
            "Individual stock ideas use name-only and historical quality screens. Optional SEC matches identify filers, NOT verified security classes or validated return forecasts.",
            "Filer SIC codes are current SEC industry categories, not a comprehensive sector or segment-exposure model.",
            "Historical correlations can change rapidly; they are not predictions or an independent safety guarantee.",
            "Fractional shares use past adjusted closes, NOT executable quotes. Actual shares, orders, fees and fractional-trading support may differ.",
            "A 30% market drop is a stress example, not the worst possible loss or a forecast.",
            "Risk-dollar cap is a long-only exposure limit, not a calculated probability of loss or downside guarantee.",
            "Cash is modeled at nominal face value; inflation and other cash risks are excluded.",
            "Horizon percentages are illustrative policy examples, not tested or optimized portfolios.",
            "Predictive odds may become available only after predeclared walk-forward research gates; historic skill does not guarantee future returns.",
            "No brokerage orders are created.",
        ],
    }
