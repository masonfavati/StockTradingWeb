"""Write a prospective scanner research record *before* its future outcome.

Never call this a proven backtest, predicted return, or an investment order.
The scan uses current-at-run Alpaca SIP `all` adjusted historical data.
"""

import hashlib
import json
import os
from collections.abc import Mapping, Sequence
from datetime import UTC, date, datetime
from pathlib import Path
from typing import Any

SCHEMA_VERSION = "forward-research-record-v1"
SCANNER_RULE_ID = "completed-sip-all-descriptive-momentum-volatility-v1"


def universe_digest(symbols: Sequence[str]) -> str:
    """Fingerprint the precise sorted eligible symbol set, not its size alone."""
    if not symbols or len(set(symbols)) != len(symbols):
        raise ValueError("Universe must contain unique symbols")
    if any(not symbol or not isinstance(symbol, str) for symbol in symbols):
        raise ValueError("Invalid symbol in recorded universe")
    return hashlib.sha256("\n".join(sorted(symbols)).encode("utf-8")).hexdigest()


def build_forward_record(
    *,
    started_at: datetime,
    finished_at: datetime,
    latest_completed_session: date,
    latest_scan_session: date | None,
    directory_size: int,
    considered: int,
    processed: int,
    qualified: int,
    symbol_digest: str,
    candidates: Sequence[Mapping[str, Any]],
    horizon: int,
    excluded_invalid_core_symbols: int = 0,
    invalid_core_records: int = 0,
    invalid_core_examples: Sequence[str] = (),
) -> dict[str, Any]:
    """Freeze a descriptive shortlist; reject partial/stale/future scans.

    Candidate dictionaries must come from the scanner's real output, not a
    synthetic post-hoc selection. A no-qualifying-stock record is valid.
    """
    if started_at.tzinfo is None or finished_at.tzinfo is None:
        raise ValueError("Recording timestamps must include a time zone")
    started = started_at.astimezone(UTC)
    finished = finished_at.astimezone(UTC)
    if finished < started:
        raise ValueError("Finish time precedes start time")
    if not 1 <= horizon <= 252:
        raise ValueError("Horizon must be 1 to 252 trading sessions")
    if directory_size < considered or considered < 1 or processed != considered:
        raise ValueError("Refusing an incomplete market scan")
    if not isinstance(symbol_digest, str) or len(symbol_digest) != 64:
        raise ValueError("The recorded universe must have a SHA-256 fingerprint")
    if qualified < len(candidates) or len(candidates) > 20:
        raise ValueError("Candidate counts do not match a scanner shortlist")
    if (
        excluded_invalid_core_symbols < 0
        or excluded_invalid_core_symbols > considered
        or invalid_core_records < excluded_invalid_core_symbols
        or (excluded_invalid_core_symbols == 0 and invalid_core_records != 0)
        or len(invalid_core_examples) > 5
        or any(not isinstance(item, str) or not item for item in invalid_core_examples)
    ):
        raise ValueError("Invalid market-data exclusion coverage")
    if latest_completed_session >= finished.date():
        # Conservative: a completed daily observation must predate record time.
        raise ValueError("Completed market session must precede record UTC date")
    if latest_scan_session is not None and latest_scan_session > latest_completed_session:
        raise ValueError("Scanner contains a future or incomplete session")
    if latest_scan_session != latest_completed_session:
        raise ValueError("Scanner cannot confirm current completed-session coverage")
    symbols: set[str] = set()
    frozen: list[dict[str, Any]] = []
    for item in candidates:
        symbol = item.get("symbol")
        last_session = item.get("last_session")
        score = item.get("research_score")
        if (
            not isinstance(symbol, str) or not symbol or symbol in symbols
            or last_session != latest_completed_session.isoformat()
            or isinstance(score, bool) or not isinstance(score, (int, float))
        ):
            raise ValueError("Shortlist contains duplicate, stale, or invalid candidate")
        symbols.add(symbol)
        # JSON round trip strips arbitrary user-specific Python objects, and
        # rejects NaN/Infinity rather than writing invalid research evidence.
        frozen.append(json.loads(json.dumps(dict(item), allow_nan=False)))
    return {
        "schema_version": SCHEMA_VERSION,
        "research_rule": SCANNER_RULE_ID,
        "started_at_utc": started.isoformat(),
        "recorded_at_utc": finished.isoformat(),
        "last_completed_market_session": latest_completed_session.isoformat(),
        "scanner_latest_session": latest_scan_session.isoformat() if latest_scan_session else None,
        "hypothetical_next_session_open_entry": True,
        "hypothetical_holding_sessions": horizon,
        "data_provider": "alpaca",
        "feed": "sip",
        "adjustment": "all",
        "data_is_live": False,
        "directory_entries": directory_size,
        "eligible_symbols_considered": considered,
        "symbols_processed": processed,
        "qualified_by_scanner": qualified,
        "excluded_due_to_invalid_core_bars": excluded_invalid_core_symbols,
        "invalid_core_bar_records": invalid_core_records,
        "invalid_core_examples": list(invalid_core_examples),
        "eligible_symbol_sha256": symbol_digest,
        "shortlist": frozen,
        "warnings": [
            "Research shortlist only. Not a buy recommendation, price forecast or probability.",
            "SIP all-adjusted data is known at recording time, not point-in-time historical data.",
            "Current assets may include complex instruments; security types are not independently verified.",
            "Prospective future outcomes have NOT been observed or evaluated.",
            "No spreads, split-aware executions, delistings, fees or dividends are modeled here.",
            "Local record timestamps and hashes are not independent proof of creation time.",
            "Eligible symbols were queried, but any symbol with malformed core OHLCV was excluded entirely from ranking.",
        ],
    }


def write_forward_record(path: Path, body: Mapping[str, Any]) -> str:
    """Create a private non-overwritable JSON research record, atomically.

    We intentionally do not implement overwrite or append. A SHA-256 checksum
    detects accidental changes but is NOT a cryptographic timestamp authority.
    """
    canonical = json.dumps(dict(body), sort_keys=True, separators=(",", ":"), allow_nan=False)
    digest = hashlib.sha256(canonical.encode("utf-8")).hexdigest()
    payload = {**body, "content_sha256": digest}
    data = (json.dumps(payload, indent=2, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
    descriptor = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    try:
        with os.fdopen(descriptor, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
    except (OSError, KeyboardInterrupt):
        path.unlink(missing_ok=True)
        raise
    return digest
