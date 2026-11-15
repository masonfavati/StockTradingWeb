"""Optional SEC ticker-to-filer cross-reference for illustrative stock slices.

A CIK identifies an EDGAR filer, *not* a verified common-share security type,
industry, or historical ticker entitlement. All references are locally imported.
No SEC network calls occur when calculating a budget plan.
"""

import hashlib
import json
import os
import re
import tempfile
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REFERENCE_FILENAME = "sec_ticker_reference_v1.json"
REFERENCE_VERSION = "sec-ticker-crossref-v1"
OFFICIAL_SOURCE = "https://www.sec.gov/files/company_tickers_exchange.json"
MAX_REFERENCE_BYTES = 8_000_000
MAX_AGE = timedelta(days=30)
_SYMBOL = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")


class SecIdentityError(ValueError):
    """Invalid, inconsistent, or unsafe SEC ticker-reference input."""


@dataclass(frozen=True)
class SecFiler:
    cik: str
    name: str
    exchange: str


@dataclass(frozen=True)
class SecReference:
    imported_at_utc: datetime
    source_sha256: str
    entries: Mapping[str, tuple[SecFiler, ...]]


def _no_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecIdentityError("Duplicate SEC JSON key")
        result[key] = value
    return result


def _no_constants(_value: str) -> None:
    raise SecIdentityError("Non-finite SEC JSON value")


def _parse_json(raw: bytes) -> Any:
    try:
        return json.loads(
            raw.decode("utf-8"), object_pairs_hook=_no_duplicates,
            parse_constant=_no_constants,
        )
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SecIdentityError("SEC reference is not valid JSON") from exc


def _read_file(path: Path, *, optional: bool = False) -> bytes | None:
    if optional and not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise SecIdentityError("SEC reference must be an ordinary file")
    size = path.stat().st_size
    if size < 1 or size > MAX_REFERENCE_BYTES:
        raise SecIdentityError("SEC reference file size outside allowed bounds")
    return path.read_bytes()


def _extract_rows(body: Any) -> list[list[Any]]:
    if not isinstance(body, dict) or body.get("fields") != [
        "cik", "name", "ticker", "exchange",
    ] or not isinstance(body.get("data"), list):
        raise SecIdentityError("Not the SEC company_tickers_exchange.json format")
    rows = body["data"]
    if len(rows) > 150_000:
        raise SecIdentityError("SEC reference has too many rows")
    checked: list[list[Any]] = []
    for row in rows:
        if not isinstance(row, list) or len(row) != 4:
            raise SecIdentityError("Malformed SEC reference row")
        checked.append(row)
    return checked


def _filer_rows(rows: Sequence[Sequence[Any]]) -> dict[str, tuple[SecFiler, ...]]:
    indexed: dict[str, set[SecFiler]] = {}
    for cik, name, symbol, exchange in rows:
        if (
            isinstance(cik, bool) or not isinstance(cik, int)
            or not (1 <= cik <= 9_999_999_999)
            or not isinstance(name, str) or not name.strip() or len(name) > 300
            or not isinstance(exchange, str) or not exchange.strip() or len(exchange) > 100
            or not isinstance(symbol, str)
        ):
            raise SecIdentityError("Invalid SEC filer entry")
        # Do not guess how a provider maps punctuation or other ticker syntax.
        # Unsupported symbols cannot be matched, rather than auto-normalized.
        if _SYMBOL.fullmatch(symbol) is None:
            continue
        indexed.setdefault(symbol, set()).add(
            SecFiler(f"{cik:010d}", name.strip(), exchange.strip())
        )
    return {symbol: tuple(sorted(filers, key=lambda f: (f.cik, f.exchange, f.name)))
            for symbol, filers in indexed.items()}


def _canonical_file(body: Mapping[str, Any]) -> bytes:
    return (json.dumps(body, sort_keys=True, separators=(",", ":"),
                       ensure_ascii=False, allow_nan=False) + "\n").encode("utf-8")


def install_reference(source: Path, directory: Path, *, replace: bool = False,
                      now: datetime | None = None) -> SecReference:
    """Import SEC's official bulk file, keeping a pinned local copy + digest."""
    raw = _read_file(source)
    assert raw is not None
    rows = _extract_rows(_parse_json(raw))
    indexed = _filer_rows(rows)
    if not indexed:
        raise SecIdentityError("SEC file has no supported ticker entries")
    timestamp = now or datetime.now(UTC)
    if timestamp.utcoffset() is None:
        raise SecIdentityError("Import time must have a timezone")
    payload: dict[str, Any] = {
        "schema_version": REFERENCE_VERSION,
        "source_url": OFFICIAL_SOURCE,
        "source_sha256": hashlib.sha256(raw).hexdigest(),
        "imported_at_utc": timestamp.astimezone(UTC).isoformat(),
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": rows,
    }
    payload["content_sha256"] = hashlib.sha256(_canonical_file(payload)).hexdigest()
    content = _canonical_file(payload)
    if len(content) > MAX_REFERENCE_BYTES:
        raise SecIdentityError("Pinned SEC reference exceeds size limit")
    reference_dir = directory / "reference"
    if reference_dir.is_symlink():
        raise SecIdentityError("SEC reference directory cannot be a symlink")
    reference_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = reference_dir / REFERENCE_FILENAME
    if destination.is_symlink() or (destination.exists() and not replace):
        raise SecIdentityError("SEC reference already exists; use --replace for an explicit update")
    handle, temporary = tempfile.mkstemp(prefix=".sec-reference-", dir=reference_dir)
    try:
        with os.fdopen(handle, "wb") as file:
            file.write(content)
            file.flush()
            os.fsync(file.fileno())
        os.chmod(temporary, 0o600)
        if not replace and destination.exists():
            raise SecIdentityError("SEC reference already exists")
        os.replace(temporary, destination)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    return SecReference(timestamp.astimezone(UTC), payload["source_sha256"], indexed)


def load_reference(directory: Path) -> SecReference | None:
    """Read a pinned cross-reference and fail on any internal inconsistency."""
    reference_dir = directory / "reference"
    if reference_dir.is_symlink():
        raise SecIdentityError("SEC reference directory cannot be a symlink")
    raw = _read_file(reference_dir / REFERENCE_FILENAME, optional=True)
    if raw is None:
        return None
    body = _parse_json(raw)
    if (not isinstance(body, dict) or body.get("schema_version") != REFERENCE_VERSION
            or body.get("source_url") != OFFICIAL_SOURCE):
        raise SecIdentityError("Unsupported SEC reference metadata")
    digest = body.get("source_sha256")
    if not isinstance(digest, str) or re.fullmatch(r"[0-9a-f]{64}", digest) is None:
        raise SecIdentityError("Invalid SEC source checksum")
    imported_raw = body.get("imported_at_utc")
    if not isinstance(imported_raw, str):
        raise SecIdentityError("Missing SEC import timestamp")
    try:
        imported = datetime.fromisoformat(imported_raw)
    except ValueError as exc:
        raise SecIdentityError("Invalid SEC import timestamp") from exc
    if imported.utcoffset() is None:
        raise SecIdentityError("SEC import timestamp must include timezone")
    expected_checksum = body.get("content_sha256")
    canonical = {key: value for key, value in body.items() if key != "content_sha256"}
    if expected_checksum != hashlib.sha256(_canonical_file(canonical)).hexdigest():
        raise SecIdentityError("Pinned SEC reference content was modified")
    rows = _extract_rows(body)
    indexed = _filer_rows(rows)
    # This checksum detects accidental editing, NOT adversarial tampering.
    # The source digest is provenance metadata, not a guarantee of timeliness.
    if not indexed:
        raise SecIdentityError("Empty SEC reference")
    return SecReference(imported.astimezone(UTC), digest, indexed)


def _recognized_exchange(value: str) -> bool:
    return value.upper() in {"NASDAQ", "NYSE", "NYSE AMERICAN"}


def review_sec_identity(
    symbols: Sequence[str], reference: SecReference | None, *,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Cross-reference at most two proposed stock tickers; never infer share type."""
    current = now or datetime.now(UTC)
    if current.utcoffset() is None:
        raise SecIdentityError("Review time must have timezone")
    requested = list(symbols)
    if len(requested) > 2 or len(set(requested)) != len(requested):
        raise SecIdentityError("SEC review expects up to two distinct tickers")
    approved: list[str] = []
    matches: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    status = "checked"
    if reference is None:
        status = "unavailable"
    elif current - reference.imported_at_utc > MAX_AGE or current < reference.imported_at_utc:
        status = "stale"
    used_cik: set[str] = set()
    for symbol in requested:
        if status != "checked":
            excluded.append({"symbol": symbol, "reason": f"sec_reference_{status}"})
            continue
        assert reference is not None
        candidate_rows = reference.entries.get(symbol, ())
        # Even if multiple SEC rows share a CIK, different underlying entries
        # (e.g. exchanges/classes) require further confirmation. Fail closed.
        if not candidate_rows:
            excluded.append({"symbol": symbol, "reason": "sec_ticker_not_found"})
            continue
        if len(candidate_rows) != 1:
            excluded.append({"symbol": symbol, "reason": "sec_ticker_ambiguous"})
            continue
        entry = candidate_rows[0]
        if not _recognized_exchange(entry.exchange):
            excluded.append({"symbol": symbol, "reason": "sec_exchange_not_supported"})
            continue
        if entry.cik in used_cik:
            excluded.append({"symbol": symbol, "reason": "same_sec_filer_as_prior_stock"})
            continue
        used_cik.add(entry.cik)
        approved.append(symbol)
        matches.append({
            "symbol": symbol, "cik": entry.cik,
            "sec_filer_name": entry.name, "sec_exchange": entry.exchange,
        })
    return {
        "version": REFERENCE_VERSION,
        "status": status,
        "requested_symbols": requested,
        "approved_symbols": approved,
        "matches": matches,
        "excluded": excluded,
        "source_url": OFFICIAL_SOURCE,
        "source_sha256": reference.source_sha256 if reference is not None else None,
        "imported_at_utc": reference.imported_at_utc.isoformat() if reference is not None else None,
        "caveat": (
            "Official SEC ticker-to-CIK filer cross-reference as imported locally; "
            "not proof of common-stock security type, beneficial ownership, "
            "industry/sector exposure, historical identity, or expected returns. "
            "Ticker punctuation is not automatically normalized."
        ),
    }
