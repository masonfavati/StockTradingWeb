"""Visual budget, exploratory growth estimates, and a private manual portfolio.

No broker orders; no profitable-outcome guarantees; never replace real prices
with guessed ones. One completed daily-history download is shared per plan.
"""

import time
from collections import OrderedDict
from datetime import UTC, date, datetime
from decimal import Decimal
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, StrictBool

from app.analysis.budget_planner import BudgetPlanError, make_budget_plan
from app.analysis.growth_allocation import build_diversified_research_plan
from app.analysis.historical_growth import (
    GrowthError,
    PricePoint,
    compare_forecasts,
    forecast_price_history,
)
from app.analysis.investing_service import (
    InvestingDataError,
    fetch_growth_histories,
    price_review_alerts,
)
from app.analysis.investment_quality import screen_budget_candidates
from app.analysis.max_growth_search import build_max_model_growth_plan
from app.analysis.portfolio_comparison import compare_scenarios
from app.analysis.portfolio_journal import (
    PortfolioError,
    add_trade,
    load_trades,
    summary_trades,
    undo_last_trade,
)
from app.analysis.stock_history_chart import ChartHistoryError, validate_symbol
from app.api.research_dashboard import _latest_saved_checkpoint, _research_root
from app.api.scanner import _MANAGER
from app.core.config import Settings
from app.market_data.history_client import AlpacaHistoryClient, HistoricalDataError


def _require_local(request: Request) -> None:
    """Holdings contain private financial records; no public unauthenticated API."""
    host = request.client.host if request.client else None
    if host not in ("127.0.0.1", "::1", "localhost", "testclient"):
        raise HTTPException(status_code=403, detail="Private portfolio access is local-only.")


router = APIRouter(prefix="/api/investing", tags=["Experimental investing workspace"])
_CACHE_LOCK = Lock()
_CACHE: OrderedDict[tuple[str, ...], tuple[float, dict[str, list[PricePoint]]]] = OrderedDict()


class GrowthPlanRequest(BaseModel):
    budget_usd: Decimal
    style: Literal["cautious", "balanced", "growth"] = "balanced"
    horizon: Literal["short", "medium", "long"] = "long"
    max_loss_usd: Decimal | None = None
    allow_exploratory: StrictBool = False
    # Empty = latest actual market-wide scan; named stocks = user-supplied comparison.
    symbols: list[str] = Field(default_factory=list, max_length=10)


class ManualTradeRequest(BaseModel):
    action: Literal["buy", "sell", "split"]
    symbol: str
    date: date
    shares: Decimal | None = None
    price_usd: Decimal | None = None
    fee_usd: Decimal = Decimal(0)
    ratio: Decimal | None = None


def _history(
    symbols: list[str], *, adjustment: Literal["all", "raw"], days: int = 1850,
) -> dict[str, list[PricePoint]]:
    today = datetime.now(UTC)
    key = (adjustment, str(days), str(today.date()), *sorted(symbols))
    tick = time.monotonic()
    with _CACHE_LOCK:
        prior = _CACHE.get(key)
        if prior and tick - prior[0] < 900:
            _CACHE.move_to_end(key)
            return prior[1]
    # Do not hold a mutex through the Alpaca network call.
    data = fetch_growth_histories(
        AlpacaHistoryClient(Settings()), symbols, now=today, calendar_days=days,
        adjustment=adjustment,
    )
    with _CACHE_LOCK:
        _CACHE[key] = (tick, data)
        _CACHE.move_to_end(key)
        while len(_CACHE) > 8:
            _CACHE.popitem(last=False)
    return data


def _research_candidates() -> tuple[list[dict[str, Any]], dict[str, str]]:
    now = datetime.now(UTC)
    snap = _MANAGER.snapshot()
    probe = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        scan_state=snap.state, scan_completed_at=snap.completed_at,
        scan_latest_session=snap.latest_session, candidates=snap.candidates, now=now,
    )
    if probe["scan_usable_for_ideas"]:
        # Prefer the separately vetted full-market pool: the scanner's public
        # top 20 is truncated BEFORE quality screening and can hide qualified
        # lower-ranked stocks. Recheck at request time; never trust raw rows.
        investing_pool = getattr(snap, "investing_candidates", None) or snap.candidates
        eligible, _ = screen_budget_candidates(
            investing_pool, snap.latest_session, max_selections=20,
        )
        if eligible:
            return [dict(row) for row in eligible], {
                "source": "latest_full_market_scan", "session": snap.latest_session or "",
            }
    try:
        saved = _latest_saved_checkpoint(_research_root())
    except (OSError, ValueError) as exc:
        raise InvestingDataError("Saved research could not be verified.") from exc
    if saved is not None:
        probe = make_budget_plan(
            Decimal(100), "balanced", allow_experimental_stocks=True,
            scan_state="complete", scan_completed_at=saved["recorded_at_utc"],
            scan_latest_session=saved["signal_session"], candidates=saved["candidates"], now=now,
        )
        if probe["scan_usable_for_ideas"]:
            eligible, _ = screen_budget_candidates(
                saved["candidates"], saved["signal_session"], max_selections=20,
            )
            if eligible:
                return [dict(row) for row in eligible], {
                    "source": "verified_saved_market_scan", "session": saved["signal_session"],
                }
    raise InvestingDataError(
        "No fresh full-market shortlist is available. A new market search is needed "
        "before claiming to compare the strongest candidates."
    )


def _planning_histories(symbols: list[str]) -> dict[str, list[PricePoint]]:
    """Download a broader research pool in bounded provider-safe chunks.

    Keep the already-tested general history API limit of 12 symbols per call
    (including SPY). This is NOT exhaustive full-market forecasting.
    """
    if len(symbols) > 20:
        raise InvestingDataError("At most 20 quality-screened stocks may receive estimates.")
    if len(symbols) <= 11:
        return _history([*symbols, "SPY"], adjustment="all")
    results: dict[str, list[PricePoint]] = {}
    for start in range(0, len(symbols), 11):
        batch = symbols[start : start + 11]
        if start == 0:
            batch = [*batch, "SPY"]
        results.update(_history(batch, adjustment="all"))
    return results


@router.post("/plan")
def growth_plan(request: GrowthPlanRequest) -> dict[str, Any]:
    try:
        if request.symbols:
            symbols = [validate_symbol(s) for s in request.symbols]
            if len(set(symbols)) != len(symbols) or "SPY" in symbols:
                raise InvestingDataError("Enter distinct stock tickers; SPY is automatically included.")
            selection = {"source": "user_selected_tickers_not_entire_market", "session": ""}
        else:
            try:
                eligible, selection = _research_candidates()
            except InvestingDataError as exc:
                # The first 409 deliberately starts a full-market scan. Once a
                # scan has FINISHED, however, no eligible stock is a legitimate
                # result, not a reason to block the basic budget illustration
                # or trigger an expensive repeat scan. Fail closed for stocks.
                scan = _MANAGER.snapshot()
                if (
                    not str(exc).startswith("No fresh full-market shortlist")
                    or scan.state != "complete"
                ):
                    raise
                eligible = []
                review = getattr(scan, "investing_quality_review", {})
                examined = review.get("screened_count")
                exclusions = review.get("excluded_counts")
                details = ""
                if type(examined) is int and examined >= 0 and isinstance(exclusions, dict):
                    # Aggregate counts are from the completed scanner, not
                    # invented explanations for individual securities.
                    labels = {
                        "unverified_share_type": "unverified common-share identity",
                        "outdated_session": "outdated price sessions",
                        "below_price_floor": "low adjusted prices",
                        "below_liquidity_screen": "insufficient historical dollar volume",
                        "above_volatility_screen": "excessive historical volatility",
                        "outside_drawdown_screen": "large historical drawdowns",
                        "missing_or_invalid_metrics": "missing or invalid price metrics",
                        "repeated_apparent_issuer": "repeated apparent issuers",
                    }
                    ranked_reasons = sorted(
                        ((count, labels.get(key, key.replace("_", " ")))
                         for key, count in exclusions.items()
                         if type(count) is int and count > 0),
                        reverse=True,
                    )
                    if ranked_reasons:
                        reasons = "; ".join(
                            f"{label}: {count:,}" for count, label in ranked_reasons[:3]
                        )
                        details = (
                            f" Checked {examined:,} preliminary research candidates "
                            f"against additional quality rules. Leading exclusions: {reasons}."
                        )
                    else:
                        details = f" Checked {examined:,} preliminary research candidates."
                selection = {
                    "source": "completed_scan_no_verified_shortlist",
                    "session": scan.latest_session or "",
                    "note": (
                        "The market search finished, but no current individual-stock "
                        "shortlist passed the required checks." + details + " "
                        "This illustration uses a diversified market-fund example "
                        "and cash only; no stock picks were invented."
                    ),
                }
            symbols = [row["symbol"] for row in eligible[:20]]
        if not symbols and selection["source"] != "completed_scan_no_verified_shortlist":
            raise InvestingDataError("No qualifying stock candidates were available.")
        histories = _planning_histories(symbols)
        spy = forecast_price_history(histories["SPY"])
        period = {"short": "1m", "medium": "3m", "long": "6m"}[request.horizon]
        if (spy["status"] != "exploratory_estimates" or period not in spy["horizons"]
                or (datetime.now(UTC).date() - histories["SPY"][-1].day).days > 7):
            raise InvestingDataError("Not enough verified historical prices for a useful market reference.")
        forecasts = {symbol: forecast_price_history(histories[symbol]) for symbol in symbols}
        ranking = compare_forecasts(forecasts, period, histories)
        ranking = [row for row in ranking if
                   (datetime.now(UTC).date() - histories[row["symbol"]][-1].day).days <= 7]
        plan = build_diversified_research_plan(
            request.budget_usd, style=request.style, horizon=request.horizon,
            max_loss_usd=request.max_loss_usd,
            # Arbitrary user-entered symbols lack the full market's quality
            # and security-type screening. Compare forecasts, but NEVER assign
            # experimental buying dollars from that unscreened route.
            allow_exploratory=(request.allow_exploratory and selection["source"] in (
                "latest_full_market_scan", "verified_saved_market_scan",
            )),
            ranked=ranking, histories=histories, benchmark=spy,
        )
        # Build both comparison alternatives from the *same* downloaded
        # histories and forecasts. Nothing here triggers another scan or a
        # second Alpaca request. The stock-only version remains read-only
        # and stock allocations require a quality-screened full-market scan.
        stock_allocation_authorized = bool(
            request.allow_exploratory and selection["source"] in (
                "latest_full_market_scan", "verified_saved_market_scan",
            )
        )
        comparison_plans = {"combined": plan}
        comparison_plans["core_only"] = build_diversified_research_plan(
            request.budget_usd, style=request.style, horizon=request.horizon,
            max_loss_usd=request.max_loss_usd, allow_exploratory=False,
            ranked=ranking, histories=histories, benchmark=spy,
            allocation_mode="core_only",
        )
        # Unlike the ordinary risk-adjusted basket, this searches EVERY
        # screened stock subset (up to four of the <=20 forecasts), in both
        # stock-only and SPY+stock structures, and maximizes the displayed
        # experimental model dollars under the same money/risk safety caps.
        # Do not give an unverified user-entered ticker buying dollars.
        comparison_plans["max_model_change"] = build_max_model_growth_plan(
            request.budget_usd, style=request.style, horizon=request.horizon,
            max_loss_usd=request.max_loss_usd,
            allow_exploratory=stock_allocation_authorized,
            ranked=ranking, histories=histories, benchmark=spy,
        )
        scenario_comparison = compare_scenarios(
            comparison_plans, histories,
            stock_allocation_authorized=stock_allocation_authorized,
        )
        if request.allow_exploratory and selection["source"] == "user_selected_tickers_not_entire_market":
            plan["warning"] += (" User-selected symbols are not security-type verified "
                                "and cannot receive experimental stock allocations.")
        if "note" in selection:
            plan["warning"] += " " + selection["note"]
    except (ChartHistoryError, GrowthError, InvestingDataError, BudgetPlanError, ValueError) as exc:
        message = str(exc)
        status = 409 if "No fresh full-market shortlist" in message else 422
        raise HTTPException(status_code=status, detail=message) from exc
    except (HistoricalDataError, OSError) as exc:
        raise HTTPException(
            status_code=503, detail="Historical price provider unavailable; no estimates were invented.",
        ) from exc
    # The 180-day market scanner inspects the active universe. The expensive
    # five-year forecast is only applied to up to 20 stocks chosen *before*
    # the model estimates growth. Never label this as an all-stock forecast.
    scope: dict[str, Any] = {
        "complete_market_forecast": False,
        "market_symbols_screened": None,
        "preliminary_candidates_quality_screened": None,
        "symbols_selected_for_forecast": len(symbols),
        "symbols_with_estimates": len(ranking),
    }
    if selection["source"] in (
        "latest_full_market_scan", "completed_scan_no_verified_shortlist",
    ):
        snapshot = _MANAGER.snapshot()
        if snapshot.state == "complete" and snapshot.latest_session == selection["session"]:
            count = getattr(snapshot, "processed", None)
            if type(count) is int and count >= 0:
                scope["market_symbols_screened"] = count
            quality = getattr(snapshot, "investing_quality_review", None)
            if isinstance(quality, dict):
                screened = quality.get("screened_count")
                if type(screened) is int and screened >= 0:
                    scope["preliminary_candidates_quality_screened"] = screened
    return {
        "version": "3k-visual-growth-research-v1", "plan": plan,
        "scenario_comparison": scenario_comparison,
        "ranking_scope": scope,
        "selection": selection, "ranked_stocks": ranking,
        "benchmark": {
            "symbol": "SPY", "horizon": period,
            "estimated_change_pct": spy["horizons"][period]["estimated_change_pct"],
        },
        "preview_history": {
            symbol: [
                {"date": point.day.isoformat(), "adjusted_close": round(point.close, 4)}
                for point in histories[symbol][-100:]
            ] for symbol in symbols[:6] if symbol in histories
        },
        "history_source": "Alpaca completed daily SIP bars, adjusted using information known today",
        "evidence_grade": "experimental_not_prospectively_validated",
        "important": (
            "The market-wide scanner checks short-window trading evidence. The five-year "
            "historical model then forecasts ONLY up to 20 quality-screened candidates "
            "or user-selected stocks, NOT every stock in the market. The estimated growth "
            "period (1, 3 or 6 months) is shorter than a multi-year holding period. "
            "Historical analogues are unvalidated predictions, "
            "not a guarantee of maximum growth or loss avoidance."
        ),
    }


@router.get("/portfolio", dependencies=[Depends(_require_local)])
def manual_portfolio() -> dict[str, Any]:
    try:
        rows = load_trades(_research_root())
        return {"summary": summary_trades(rows), "trades": rows[-100:]}
    except (OSError, PortfolioError, ChartHistoryError) as exc:
        raise HTTPException(status_code=503, detail="Manual portfolio records are unavailable.") from exc


@router.post("/portfolio/trades", status_code=201, dependencies=[Depends(_require_local)])
def log_trade(request: ManualTradeRequest) -> dict[str, Any]:
    try:
        trade = add_trade(
            _research_root(), action=request.action, symbol=request.symbol,
            day=request.date, shares=request.shares, price_usd=request.price_usd,
            fee_usd=request.fee_usd, ratio=request.ratio,
        )
    except (ValueError, PortfolioError, ChartHistoryError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Unable to write local portfolio.") from exc
    return {"saved": True, "trade": trade}


@router.delete("/portfolio/trades/{trade_id}", dependencies=[Depends(_require_local)])
def undo_trade(trade_id: str) -> dict[str, bool]:
    try:
        undo_last_trade(_research_root(), trade_id)
    except (ValueError, PortfolioError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except OSError as exc:
        raise HTTPException(status_code=503, detail="Unable to change local portfolio.") from exc
    return {"removed": True}


@router.post("/portfolio/refresh", dependencies=[Depends(_require_local)])
def refresh_manual_portfolio() -> dict[str, Any]:
    """Explicitly request completed daily quotes; no live broker or auto sell."""
    try:
        rows = load_trades(_research_root())
        current = summary_trades(rows)
        symbols = [row["symbol"] for row in current["holdings"]]
        if len(symbols) > 10:
            raise PortfolioError("Automatic price checks support at most ten holdings.")
        if not symbols:
            return {"summary": current, "alerts": [], "quotes_source": None}
        # Raw prices are closest to actual trade fills; stock split changes
        # still require a manual share-count adjustment event in this ledger.
        histories = _history(symbols, adjustment="raw", days=400)
        quotes = {
            symbol: (Decimal(str(prices[-1].close)), prices[-1].day.isoformat())
            for symbol, prices in histories.items() if prices
        }
        updated = summary_trades(rows, quotes)
        alerts = price_review_alerts(updated["holdings"], histories)
        return {
            "summary": updated, "alerts": alerts,
            "quotes_source": "Alpaca raw last completed daily prices; not live/executable",
            "alerts_are_predictions": False,
            "alert_explanation": (
                "Review flags use predefined historical drop, concentration, and recorded-loss "
                "thresholds; they cannot identify the perfect time to sell or prevent losses."
            ),
        }
    except (PortfolioError, ChartHistoryError, InvestingDataError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (HistoricalDataError, OSError) as exc:
        raise HTTPException(status_code=503, detail="Price refresh unavailable; holdings unchanged.") from exc
