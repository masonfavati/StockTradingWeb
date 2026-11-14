"""Save a dated, forward-looking market-scanner research checkpoint.

Run on your Mac after the last completed session, BEFORE the next market open:
 uv run python -m app.analysis.forward_cli --out ~/StockTradingWebResearch/scan.json

This makes NO trades and does not calculate any future outcomes.
"""

import argparse
import re
from dataclasses import asdict
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from app.analysis.forward_record import build_forward_record, universe_digest, write_forward_record
from app.analysis.market_scan import scan_market
from app.core.config import Settings
from app.market_data.asset_search import AlpacaAssetCatalog, SearchResult
from app.market_data.history_audit import get_market_calendar
from app.market_data.history_client import AlpacaHistoryClient
from app.market_data.history_import import completed_session_cutoff

_VALID_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")


class ObservedCatalog:
    """Use a fresh provider directory and retain exactly what the scan saw."""

    def __init__(self) -> None:
        self._catalog = AlpacaAssetCatalog()
        self.rows: list[SearchResult] | None = None

    def list_active(self) -> list[SearchResult]:
        self.rows = self._catalog.list_active()
        return list(self.rows)

    def eligible_symbols(self) -> list[str]:
        if self.rows is None:
            raise ValueError("Directory was not loaded")
        return sorted({
            asset.symbol for asset in self.rows
            if asset.tradable and _VALID_SYMBOL.fullmatch(asset.symbol) is not None
        })


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", required=True, type=Path, help="New JSON path; never overwritten")
    parser.add_argument("--horizon", type=int, default=20, help="Future holding sessions, 1–252")
    args = parser.parse_args()
    if not 1 <= args.horizon <= 252:
        parser.error("--horizon must be 1–252")
    if not args.out.parent.is_dir():
        parser.error("The output directory must already exist")
    if args.out.exists():
        parser.error("Refusing to overwrite an existing prospective record")

    started = datetime.now(UTC)
    settings = Settings()
    cutoff_day = completed_session_cutoff(now=started).astimezone(ZoneInfo("America/New_York")).date()
    sessions = get_market_calendar(
        start=cutoff_day - timedelta(days=14), end=cutoff_day, settings=settings,
    )
    if not sessions:
        parser.exit(1, "No verified completed exchange session; no record saved.\n")
    expected = max(sessions)
    catalog = ObservedCatalog()
    print("Running a new complete Alpaca scan; no orders will be placed.", flush=True)
    result = scan_market(
        catalog, AlpacaHistoryClient(settings), now=started,
        progress=lambda count, total: print(f"Checked {count:,}/{total:,} eligible symbols", flush=True)
        if count == total or count % 1200 == 0 else None,
    )
    finished = datetime.now(UTC)
    eligible = catalog.eligible_symbols()
    if len(eligible) != result.considered:
        parser.exit(1, "Provider universe changed during scan; no record saved.\n")
    candidate_dicts = [
        {**asdict(row), "last_session": row.last_session.isoformat()}
        for row in result.candidates
    ]
    body = build_forward_record(
        started_at=started, finished_at=finished,
        latest_completed_session=expected,
        latest_scan_session=datetime.fromisoformat(result.latest_session).date()
        if result.latest_session else None,
        directory_size=result.directory_size, considered=result.considered,
        processed=result.processed, qualified=result.qualified,
        symbol_digest=universe_digest(eligible), candidates=candidate_dicts,
        horizon=args.horizon,
        excluded_invalid_core_symbols=result.excluded_invalid_core_symbols,
        invalid_core_records=result.invalid_core_records,
        invalid_core_examples=result.invalid_core_examples,
    )
    try:
        digest = write_forward_record(args.out, body)
    except FileExistsError:
        parser.exit(1, "Record already exists; refusing to overwrite.\n")
    print(f"Saved research record: {args.out}")
    print(f"Eligible symbols queried: {result.processed:,}/{result.considered:,}")
    print(
        f"Excluded from ranking due to invalid core OHLCV: "
        f"{result.excluded_invalid_core_symbols:,} symbol(s), "
        f"{result.invalid_core_records:,} record(s)"
    )
    for example in result.invalid_core_examples:
        print(f"  Invalid record example: {example}")
    print(f"Qualified candidates: {result.qualified:,}; saved shortlist: {len(result.candidates)}")
    print(f"Record SHA-256: {digest}")
    print("Research only. Future outcomes are UNKNOWN; this does not validate a trading strategy.")


if __name__ == "__main__":
    main()
