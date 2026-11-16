"""Bounded, read-only explanations of a frozen prospective research shortlist.

Never requests quotes, predicts returns, places orders, or authorizes a budget slice.
The budget planner independently rechecks the complete evidence requirements.
"""

import math
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from app.analysis.budget_planner import MAX_SCAN_AGE
from app.analysis.investment_quality import screen_budget_candidates
from app.market_data.sec_identity import SecReference, review_sec_identity
from app.market_data.sec_industry import SicReference, review_sec_industry

MAX_VISIBLE = 20


def _numeric(value: Any) -> float | None:
    if type(value) not in (float, int):
        return None
    try:
        number = float(value)
    except (OverflowError, ValueError):
        return None
    return number if math.isfinite(number) and abs(number) <= 1e18 else None


def _sec_facts(symbol: str, ticker: SecReference | None,
               industry: SicReference | None, now: datetime) -> tuple[dict[str, Any], dict[str, Any]]:
    """One-symbol explanations, not portfolio-wide duplicate-filer/SIC approval."""
    filer_review = review_sec_identity([symbol], ticker, now=now)
    sic_review = review_sec_industry([symbol], ticker, industry, now=now)
    filer = filer_review["matches"][0] if filer_review["matches"] else None
    sic = sic_review["matches"][0] if sic_review["matches"] else None
    return (
        {
            "status": (
                "matched" if symbol in filer_review["approved_symbols"]
                else filer_review["excluded"][0]["reason"]
            ),
            "cik": filer["cik"] if filer else None,
            "name": filer["sec_filer_name"] if filer else None,
            "exchange": filer["sec_exchange"] if filer else None,
        },
        {
            "status": (
                "matched" if symbol in sic_review["approved_symbols"]
                else sic_review["excluded"][0]["reason"]
            ),
            "code": sic["sic"] if sic else None,
            "description": sic["sic_description"] if sic else None,
        },
    )


def build_decision_desk(*, source_kind: str | None,
                        signal_session: str | None,
                        recorded_at_utc: str | None,
                        candidates: Sequence[Mapping[str, Any]],
                        ticker_reference: SecReference | None = None,
                        industry_reference: SicReference | None = None,
                        prediction_status: str = "unavailable",
                        now: datetime | None = None) -> dict[str, Any]:
    """Explain the top 20 recorded candidates; NEVER treat a screen as a recommendation."""
    current = now or datetime.now(UTC)
    if current.utcoffset() is None:
        raise ValueError("Current time must be timezone aware")
    if source_kind not in (None, "website_scan", "frozen_checkpoint"):
        raise ValueError("Unrecognized research source")
    if len(candidates) > 20_000:
        raise ValueError("Research shortlist exceeds supported bounds")
    timestamp: datetime | None = None
    if recorded_at_utc:
        try:
            timestamp = datetime.fromisoformat(recorded_at_utc)
        except (TypeError, ValueError):
            timestamp = None
    if timestamp is not None and timestamp.utcoffset() is None:
        timestamp = None
    current_time = current.astimezone(UTC)
    age: timedelta | None = current_time - timestamp.astimezone(UTC) if timestamp else None
    session_recent = False
    if signal_session is not None:
        try:
            session_day = date.fromisoformat(signal_session)
            session_age = (current.astimezone(ZoneInfo("America/New_York")).date() - session_day).days
            session_recent = 0 <= session_age <= 5
        except (TypeError, ValueError):
            pass
    source_recent = (
        age is not None and timedelta(0) <= age <= MAX_SCAN_AGE
        and session_recent
    )
    listed = candidates[:MAX_VISIBLE] if source_kind is not None else []
    selected, summary = screen_budget_candidates(listed, signal_session, max_selections=MAX_VISIBLE)
    ranked_eligible = {item["symbol"] for item in selected}
    rows: list[dict[str, Any]] = []
    for position, row in enumerate(listed, 1):
        symbol, name = row.get("symbol"), row.get("name")
        # All symbols and names are untrusted broker/record text: publish only
        # bounded, display-safe scalar values; never construct provider URLs.
        if not isinstance(symbol, str) or len(symbol) > 20 or not isinstance(name, str):
            continue
        if len(name) > 240:
            name = name[:240]
        one, detail = screen_budget_candidates([row], signal_session, max_selections=1)
        if not one:
            quality_reason = next(iter(detail["excluded_counts"]), "missing_or_invalid_metrics")
        elif symbol not in ranked_eligible:
            quality_reason = "repeated_apparent_issuer_or_ticker"
        else:
            quality_reason = None
        # SEC import files can be absent or old. This is descriptive evidence,
        # not a substitute for the planner's two-stock concentration review.
        filer, sic = _sec_facts(symbol, ticker_reference, industry_reference, current)
        rows.append({
            "rank": position,
            "symbol": symbol,
            "name": name,
            "quality_passed": quality_reason is None,
            "quality_reason": quality_reason,
            "metrics": {
                key: _numeric(row.get(key)) for key in (
                    "adjusted_close", "return_20d_pct", "return_60d_pct",
                    "annualized_volatility_pct", "drawdown_60d_pct",
                    "approx_daily_dollar_volume", "research_score",
                )
            },
            "sec_filer": filer,
            "sec_industry": sic,
        })
    return {
        "version": "research-decision-desk-v1",
        "source_kind": source_kind,
        "signal_session": signal_session if source_kind else None,
        "recorded_at_utc": recorded_at_utc if source_kind else None,
        "source_recent": bool(source_kind) and source_recent,
        "source_age_hours": round(age.total_seconds() / 3600, 1) if age is not None and age >= timedelta(0) else None,
        "considered_count": len(candidates) if source_kind else 0,
        "displayed_count": len(rows),
        "quality_passed_count": sum(row["quality_passed"] for row in rows),
        "quality_thresholds": summary["thresholds"],
        "prediction_status": prediction_status,
        "candidates": rows,
        "caveats": [
            "Scanner rank reflects historical momentum and risk heuristics, not an expected return or a buy recommendation.",
            "Adjusted closing prices and volume are historical; no live or executable quote is provided.",
            "SEC CIK and SIC evidence is current locally imported filer metadata, not point-in-time security type or full sector exposure.",
            "Individual quality and SEC facts do not include pairwise issuer, industry or correlation checks; the planner checks those separately.",
            "The planner independently evaluates freshness, user loss limits and every selected evidence gate before allocating experimental dollars.",
        ],
    }
