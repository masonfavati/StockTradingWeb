"""Read-only browser research overview and an explicitly illustrative budget tool."""

import hashlib
import json
import os
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, field_validator

from app.analysis.budget_planner import (
    BudgetPlanError,
    make_budget_plan,
    validate_budget,
    validate_max_loss,
)
from app.analysis.forward_evaluation import ForwardEvaluationError
from app.analysis.forward_journal import JournalError, entries
from app.analysis.forward_outcomes import OutcomeJournalError
from app.analysis.forward_performance import PerformanceReportError, build_performance_report
from app.api.scanner import _MANAGER
from app.market_data.history_audit import CalendarError

router = APIRouter(prefix="/api/research", tags=["Read-only investment research"])


def _research_root() -> Path:
    return Path(os.environ.get("STW_RESEARCH_DIR", str(Path.home() / "StockTradingWebResearch")))


def _unique_fields(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    value: dict[str, Any] = {}
    for key, content in pairs:
        if key in value:
            raise JournalError("Duplicate checkpoint field")
        value[key] = content
    return value


def _reject_nonfinite(_value: str) -> None:
    raise JournalError("Nonfinite checkpoint field")


def _latest_saved_checkpoint(root: Path) -> dict[str, Any] | None:
    """Return only a checksum-verified *frozen* shortlist, never outcome information."""
    rows = entries(root)
    if not rows:
        return None
    latest = max(rows, key=lambda item: item.checkpoint.recorded_at_utc)
    path = latest.record_path
    if not path.is_file() or path.is_symlink() or path.stat().st_size > 1_000_000:
        raise JournalError("Pinned checkpoint is not a safe ordinary file")
    body = json.loads(
        path.read_text(encoding="utf-8"), object_pairs_hook=_unique_fields,
        parse_constant=_reject_nonfinite,
    )
    if not isinstance(body, dict):
        raise JournalError("Pinned checkpoint is not a JSON object")
    canonical = {key: value for key, value in body.items() if key != "content_sha256"}
    digest = hashlib.sha256(json.dumps(canonical, sort_keys=True, separators=(",", ":"),
        allow_nan=False).encode()).hexdigest()
    if digest != latest.expected_sha256 or body.get("content_sha256") != digest:
        raise JournalError("Pinned research content changed")
    frozen = latest.checkpoint
    choices = body.get("shortlist")
    if not isinstance(choices, list) or len(choices) != len(frozen.shortlist):
        raise JournalError("Pinned shortlist does not match journal")
    if [row.get("symbol") for row in choices if isinstance(row, dict)] != list(frozen.shortlist):
        raise JournalError("Pinned shortlist symbols do not match journal")
    return {
        "signal_session": frozen.signal_session.isoformat(),
        "recorded_at_utc": frozen.recorded_at_utc.isoformat(),
        "research_rule": frozen.research_rule,
        "eligible_symbols_considered": body.get("eligible_symbols_considered"),
        "qualified_by_scanner": body.get("qualified_by_scanner"),
        "candidates": choices,
    }


class BudgetRequest(BaseModel):
    budget_usd: Decimal
    style: Literal["cautious", "balanced", "growth"] = "balanced"
    allow_experimental_stocks: bool = False
    horizon: Literal["short", "medium", "long"] = "long"
    max_loss_usd: Decimal | None = None

    @field_validator("max_loss_usd")
    @classmethod
    def check_loss_value(cls, value: Decimal | None) -> Decimal | None:
        if value is not None:
            try:
                validate_max_loss(value, Decimal("1000000.00"))
            except BudgetPlanError as exc:
                raise ValueError(str(exc)) from exc
        return value

    @field_validator("budget_usd")
    @classmethod
    def check_budget(cls, value: Decimal) -> Decimal:
        try:
            return validate_budget(value)
        except BudgetPlanError as exc:
            raise ValueError(str(exc)) from exc


@router.get("/overview")
def overview() -> dict[str, Any]:
    """Fetch verified research-journal summaries; NEVER fetch outcome price bars."""
    root = _research_root()
    try:
        report = build_performance_report(root)
        latest = _latest_saved_checkpoint(root)
    except (
        OSError, ValueError, JournalError, ForwardEvaluationError,
        OutcomeJournalError, PerformanceReportError, CalendarError,
    ) as exc:
        # Fail closed; don't leak checkpoint paths or private environment details.
        raise HTTPException(
            status_code=503,
            detail=f"Research journal unavailable ({type(exc).__name__}). No figures published.",
        ) from exc
    return {
        "generated_at_utc": report["generated_at_utc"],
        "registered_checkpoints": report["registered_checkpoints"],
        "status_counts": report["status_counts"],
        "groups": report["groups"],
        "latest_checkpoint": latest,
        "warnings": report["warnings"],
    }


@router.post("/budget-plan")
def budget_plan(request: BudgetRequest) -> dict[str, Any]:
    """Only registered research or an in-memory completed scan; no new scan/trade."""
    current = _MANAGER.snapshot()
    now = datetime.now(UTC)
    try:
        validate_max_loss(request.max_loss_usd, request.budget_usd)
    except BudgetPlanError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    result = make_budget_plan(
        request.budget_usd,
        request.style,
        allow_experimental_stocks=request.allow_experimental_stocks,
        horizon=request.horizon,
        max_loss_usd=request.max_loss_usd,
        scan_state=current.state,
        scan_completed_at=current.completed_at,
        scan_latest_session=current.latest_session,
        candidates=current.candidates,
        now=now,
    )
    result["source_kind"] = "website_scan" if result["scan_usable_for_ideas"] else None
    if request.allow_experimental_stocks and not result["scan_usable_for_ideas"]:
        try:
            saved = _latest_saved_checkpoint(_research_root())
        except (OSError, ValueError, JournalError, ForwardEvaluationError) as exc:
            raise HTTPException(status_code=503, detail=(
                f"Frozen research unavailable ({type(exc).__name__}); no stock ideas published."
            )) from exc
        if saved is not None:
            result = make_budget_plan(
                request.budget_usd, request.style,
                allow_experimental_stocks=True,
                horizon=request.horizon,
                max_loss_usd=request.max_loss_usd,
                scan_state="complete",
                scan_completed_at=saved["recorded_at_utc"],
                scan_latest_session=saved["signal_session"],
                candidates=saved["candidates"],
                now=now,
            )
            result["source_kind"] = (
                "frozen_checkpoint" if result["scan_usable_for_ideas"] else None
            )
    return result
