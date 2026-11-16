"""Explicit, read-only market scan; runs in a background thread per click.

This first iteration stores one job only in this Python process. It is not a
production-scale worker queue and results disappear after server restart.
"""

from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from threading import Lock
from typing import Any, Literal

from fastapi import APIRouter, BackgroundTasks
from pydantic import BaseModel, Field

from app.analysis.market_scan import scan_market
from app.core.config import Settings
from app.market_data.asset_search import get_asset_catalog
from app.market_data.history_client import AlpacaHistoryClient

router = APIRouter(prefix="/api/scanner", tags=["Market research"])
StatusKind = Literal["idle", "running", "complete", "failed"]
CACHE_DURATION = timedelta(minutes=15)


class ScannerSnapshot(BaseModel):
    state: StatusKind
    message: str
    started_at: str | None
    completed_at: str | None
    latest_session: str | None
    directory_size: int
    considered: int
    processed: int
    qualified: int
    candidates: list[dict[str, Any]]
    # Separate quality-screened picks, not the public top-20 momentum ranking.
    investing_candidates: list[dict[str, Any]] = Field(default_factory=list)
    investing_quality_review: dict[str, Any] = Field(default_factory=dict)


class ScanManager:
    def __init__(self) -> None:
        self._lock = Lock()
        self._state: StatusKind = "idle"
        self._message = "No scan has been run yet."
        self._started_at: datetime | None = None
        self._completed_at: datetime | None = None
        self._directory_size = 0
        self._considered = 0
        self._processed = 0
        self._qualified = 0
        self._latest_session: str | None = None
        self._candidates: list[dict[str, Any]] = []
        self._investing_candidates: list[dict[str, Any]] = []
        self._investing_quality_review: dict[str, Any] = {}

    def snapshot(self) -> ScannerSnapshot:
        with self._lock:
            return ScannerSnapshot(
                state=self._state,
                message=self._message,
                started_at=self._started_at.isoformat() if self._started_at else None,
                completed_at=self._completed_at.isoformat() if self._completed_at else None,
                latest_session=self._latest_session,
                directory_size=self._directory_size,
                considered=self._considered,
                processed=self._processed,
                qualified=self._qualified,
                candidates=list(self._candidates),
                investing_candidates=list(self._investing_candidates),
                investing_quality_review=dict(self._investing_quality_review),
            )

    def begin(self, *, now: datetime) -> bool:
        """Return True only when a new scan should be launched."""
        with self._lock:
            if self._state == "running":
                return False
            if (
                self._state == "complete"
                and self._completed_at is not None
                and now - self._completed_at < CACHE_DURATION
            ):
                return False
            self._state = "running"
            self._message = "Loading Alpaca's market directory..."
            self._started_at = now
            self._completed_at = None
            self._directory_size = 0
            self._considered = 0
            self._processed = 0
            self._qualified = 0
            self._latest_session = None
            self._candidates = []
            self._investing_candidates = []
            self._investing_quality_review = {}
            return True

    def progress(self, count: int, total: int) -> None:
        with self._lock:
            self._processed = count
            self._considered = total
            self._message = f"Checked {count:,} of {total:,} eligible symbols."

    def execute(self) -> None:
        try:
            result = scan_market(
                get_asset_catalog(),
                AlpacaHistoryClient(Settings()),
                now=datetime.now(UTC),
                progress=self.progress,
            )
        except Exception as exc:  # noqa: BLE001
            # A provider problem cannot be presented as a partial market scan.
            # Do not return raw exception data, credentials or request URLs.
            with self._lock:
                self._state = "failed"
                self._completed_at = datetime.now(UTC)
                self._message = f"Scan failed ({type(exc).__name__}). No ranking was published."
                self._candidates = []
                self._investing_candidates = []
                self._investing_quality_review = {}
            return

        with self._lock:
            self._state = "complete"
            self._completed_at = datetime.now(UTC)
            self._directory_size = result.directory_size
            self._considered = result.considered
            self._processed = result.processed
            self._qualified = result.qualified
            self._latest_session = result.latest_session
            self._candidates = [
                {**asdict(candidate), "last_session": candidate.last_session.isoformat()}
                for candidate in result.candidates
            ]
            self._investing_candidates = [
                {**asdict(candidate), "last_session": candidate.last_session.isoformat()}
                for candidate in result.investing_candidates
            ]
            self._investing_quality_review = dict(result.investing_quality_review)
            self._message = (
                "Completed-day research shortlist only. "
                f"Excluded {result.excluded_invalid_core_symbols:,} symbol(s) "
                "with invalid core price records. "
                "Not a validated prediction or a recommendation to buy."
            )


_MANAGER = ScanManager()


@router.get("/status", response_model=ScannerSnapshot)
def scan_status() -> ScannerSnapshot:
    return _MANAGER.snapshot()


@router.post("/scan", response_model=ScannerSnapshot, status_code=202)
def start_scan(background: BackgroundTasks) -> ScannerSnapshot:
    if _MANAGER.begin(now=datetime.now(UTC)):
        background.add_task(_MANAGER.execute)
    return _MANAGER.snapshot()
