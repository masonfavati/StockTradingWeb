"""Offline SEC SIC cross-reference; industry metadata is issuer-level, NOT a sector model.

Import SEC's public submissions.zip only when explicitly requested. No network
requests occur during planning. SIC is not a security-type, investment-suitability,
or point-in-time classification.
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
from zipfile import BadZipFile, LargeZipFile, ZipFile

from app.market_data.sec_identity import SecReference

SOURCE_URL = "https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip"
INDIVIDUAL_SOURCE_URL = "https://data.sec.gov/submissions/"
VERSION = "sec-sic-filer-industry-v1"
FILENAME = "sec_sic_reference_v1.json"
MAX_AGE = timedelta(days=30)
MAX_ARCHIVE_BYTES = 2_500_000_000
MAX_MEMBER_BYTES = 3_000_000
MAX_PIN_BYTES = 5_000_000
_MEMBER = re.compile(r"(?:submissions/)?CIK([0-9]{10})\.json\Z")
_CIK = re.compile(r"[0-9]{10}\Z")
_SIC = re.compile(r"[0-9]{4}\Z")


class SecIndustryError(ValueError):
    """SEC industry reference is incomplete, ambiguous, or unsafe."""


@dataclass(frozen=True)
class SicEntry:
    sic: str
    description: str


@dataclass(frozen=True)
class SicReference:
    imported_at_utc: datetime
    source_sha256: str
    ticker_source_sha256: str
    entries: Mapping[str, SicEntry]
    skipped_large_members: int = 0
    source_kind: str = "bulk_archive"


def _reject_duplicates(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise SecIndustryError("Duplicate SEC industry JSON key")
        result[key] = value
    return result


def _reject_constant(_value: str) -> None:
    raise SecIndustryError("Non-finite SEC industry JSON value")


def _parse(raw: bytes) -> Any:
    try:
        return json.loads(raw.decode("utf-8"), object_pairs_hook=_reject_duplicates,
                          parse_constant=_reject_constant)
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise SecIndustryError("Malformed SEC industry JSON") from exc


def _canonical(data: Mapping[str, Any]) -> bytes:
    return (json.dumps(data, sort_keys=True, separators=(",", ":"),
                       allow_nan=False, ensure_ascii=False) + "\n").encode("utf-8")


def _extract_metadata(record: Any, expected_cik: str) -> SicEntry | None:
    if not isinstance(record, dict):
        return None
    cik = record.get("cik")
    if isinstance(cik, bool) or not isinstance(cik, (str, int)):
        return None
    if not str(cik).isdigit() or f"{int(cik):010d}" != expected_cik:
        return None
    sic = record.get("sic")
    if isinstance(sic, bool) or not isinstance(sic, (str, int)):
        return None
    value = str(sic)
    description = record.get("sicDescription")
    if (_SIC.fullmatch(value) is None or value == "0000" or
            not isinstance(description, str) or not description.strip() or
            len(description) > 250):
        return None
    return SicEntry(value, description.strip())


def _desired_ciks(ticker_reference: SecReference) -> set[str]:
    return {row.cik for matches in ticker_reference.entries.values() for row in matches}


def import_industry_archive(
    source: Path, directory: Path, ticker_reference: SecReference, *,
    replace: bool = False, now: datetime | None = None,
) -> SicReference:
    """Extract only SEC SIC fields for filers present in pinned ticker reference."""
    timestamp = now or datetime.now(UTC)
    if timestamp.utcoffset() is None:
        raise SecIndustryError("Import timestamp must be timezone-aware")
    if source.is_symlink() or not source.is_file():
        raise SecIndustryError("SEC archive must be a regular file")
    if not (1 <= source.stat().st_size <= MAX_ARCHIVE_BYTES):
        raise SecIndustryError("SEC archive size outside allowed bounds")
    digest = hashlib.sha256()
    with source.open("rb") as archive_bytes:
        for chunk in iter(lambda: archive_bytes.read(1024 * 1024), b""):
            digest.update(chunk)
    desired = _desired_ciks(ticker_reference)
    extracted: dict[str, SicEntry] = {}
    seen: set[str] = set()
    oversized = 0
    try:
        with ZipFile(source) as archive:
            for info in archive.infolist():
                match = _MEMBER.fullmatch(info.filename)
                if match is None or info.is_dir():
                    continue
                cik = match.group(1)
                if cik not in desired:
                    continue
                if cik in seen:
                    # Ambiguous duplicates cannot silently decide a classification.
                    raise SecIndustryError(f"Duplicate SEC archive CIK member: {cik}")
                seen.add(cik)
                if info.file_size > MAX_MEMBER_BYTES:
                    oversized += 1
                    continue
                with archive.open(info) as member:
                    raw = member.read(MAX_MEMBER_BYTES + 1)
                if len(raw) > MAX_MEMBER_BYTES:
                    oversized += 1
                    continue
                entry = _extract_metadata(_parse(raw), cik)
                if entry is not None:
                    extracted[cik] = entry
    except (BadZipFile, LargeZipFile, OSError, RuntimeError) as exc:
        raise SecIndustryError("SEC submissions archive cannot be safely read") from exc
    if not seen:
        raise SecIndustryError("No matching SEC CIK submissions found in archive")
    if not extracted:
        raise SecIndustryError("No usable SEC SIC industry entries in archive")
    return _save_industry_reference(
        directory, ticker_reference, extracted,
        source_sha256=digest.hexdigest(), imported=timestamp, replace=replace,
        skipped_large_members=oversized, source_kind="bulk_archive",
    )


def import_industry_files(
    sources: Sequence[Path], directory: Path, ticker_reference: SecReference, *,
    replace: bool = False, now: datetime | None = None,
) -> SicReference:
    """Import 1–30 explicitly downloaded per-company SEC submissions JSON files.

    Small-file mode avoids downloading the entire SEC submissions archive. All
    files must be supplied together; this replaces the reference as one batch.
    """
    timestamp = now or datetime.now(UTC)
    if timestamp.utcoffset() is None:
        raise SecIndustryError("Import timestamp must be timezone-aware")
    if not (1 <= len(sources) <= 30):
        raise SecIndustryError("Supply 1–30 SEC per-company submissions JSON files")
    desired = _desired_ciks(ticker_reference)
    extracted: dict[str, SicEntry] = {}
    digests: dict[str, str] = {}
    for file in sources:
        if file.is_symlink() or not file.is_file():
            raise SecIndustryError("Each SEC submissions JSON must be a regular file")
        if not (1 <= file.stat().st_size <= MAX_MEMBER_BYTES):
            raise SecIndustryError("SEC submissions JSON is outside allowed size")
        raw = file.read_bytes()
        record = _parse(raw)
        cik_field = record.get("cik") if isinstance(record, dict) else None
        if isinstance(cik_field, bool) or not isinstance(cik_field, (str, int)) or not str(cik_field).isdigit():
            raise SecIndustryError("SEC submissions JSON is missing CIK")
        cik = f"{int(cik_field):010d}"
        if _CIK.fullmatch(cik) is None or cik not in desired:
            raise SecIndustryError("SEC submissions CIK is not in the pinned ticker reference")
        if cik in extracted:
            raise SecIndustryError("Repeated CIK in SEC submissions source files")
        entry = _extract_metadata(record, cik)
        if entry is None:
            raise SecIndustryError("SEC submissions file lacks valid SIC evidence")
        extracted[cik] = entry
        digests[cik] = hashlib.sha256(raw).hexdigest()
    # This is a digest of the exact imported files, NOT a claim that the
    # files came from SEC or that their timestamps are independently certified.
    collective_digest = hashlib.sha256(_canonical(digests)).hexdigest()
    return _save_industry_reference(
        directory, ticker_reference, extracted,
        source_sha256=collective_digest, imported=timestamp, replace=replace,
        skipped_large_members=0, source_kind="individual_json",
    )


def _save_industry_reference(
    directory: Path, ticker_reference: SecReference,
    extracted: Mapping[str, SicEntry], *, source_sha256: str,
    imported: datetime, replace: bool, skipped_large_members: int,
    source_kind: str,
) -> SicReference:
    source_url = SOURCE_URL if source_kind == "bulk_archive" else INDIVIDUAL_SOURCE_URL
    payload: dict[str, Any] = {
        "schema_version": VERSION,
        "source_url": source_url,
        "source_kind": source_kind,
        "source_sha256": source_sha256,
        "ticker_source_sha256": ticker_reference.source_sha256,
        "imported_at_utc": imported.astimezone(UTC).isoformat(),
        "skipped_large_members": skipped_large_members,
        "entries": {cik: {"sic": row.sic, "description": row.description}
                    for cik, row in sorted(extracted.items())},
    }
    payload["content_sha256"] = hashlib.sha256(_canonical(payload)).hexdigest()
    content = _canonical(payload)
    if len(content) > MAX_PIN_BYTES:
        raise SecIndustryError("Pinned SEC industry metadata exceeds allowed size")
    reference_dir = directory / "reference"
    if reference_dir.is_symlink():
        raise SecIndustryError("SEC reference directory cannot be a symlink")
    reference_dir.mkdir(parents=True, exist_ok=True, mode=0o700)
    destination = reference_dir / FILENAME
    if destination.is_symlink() or (destination.exists() and not replace):
        raise SecIndustryError("SEC SIC reference exists; explicitly use --replace to update")
    descriptor, temp = tempfile.mkstemp(prefix=".sec-sic-", dir=reference_dir)
    try:
        with os.fdopen(descriptor, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(temp, 0o600)
        if not replace and destination.exists():
            raise SecIndustryError("SEC SIC reference already exists")
        os.replace(temp, destination)
    finally:
        if os.path.exists(temp):
            os.unlink(temp)
    return SicReference(imported.astimezone(UTC), source_sha256,
                        ticker_reference.source_sha256, dict(extracted),
                        skipped_large_members, source_kind)


def load_industry_reference(directory: Path) -> SicReference | None:
    reference_dir = directory / "reference"
    if reference_dir.is_symlink():
        raise SecIndustryError("SEC reference directory cannot be a symlink")
    path = reference_dir / FILENAME
    if not path.exists() and not path.is_symlink():
        return None
    if path.is_symlink() or not path.is_file():
        raise SecIndustryError("SEC SIC reference must be a regular file")
    if not (1 <= path.stat().st_size <= MAX_PIN_BYTES):
        raise SecIndustryError("SEC SIC reference has unsafe size")
    body = _parse(path.read_bytes())
    if not isinstance(body, dict) or body.get("schema_version") != VERSION:
        raise SecIndustryError("Unexpected SEC SIC reference format")
    source_kind = body.get("source_kind")
    expected_url = SOURCE_URL if source_kind == "bulk_archive" else INDIVIDUAL_SOURCE_URL
    if source_kind not in ("bulk_archive", "individual_json") or body.get("source_url") != expected_url:
        raise SecIndustryError("Invalid SEC SIC source metadata")
    checksum = body.get("content_sha256")
    canonical = {key: val for key, val in body.items() if key != "content_sha256"}
    if checksum != hashlib.sha256(_canonical(canonical)).hexdigest():
        raise SecIndustryError("Pinned SEC industry reference was modified")
    for key in ("source_sha256", "ticker_source_sha256"):
        value = body.get(key)
        if not isinstance(value, str) or re.fullmatch(r"[0-9a-f]{64}", value) is None:
            raise SecIndustryError("Invalid SEC industry reference checksum")
    raw_time = body.get("imported_at_utc")
    if not isinstance(raw_time, str):
        raise SecIndustryError("Missing SEC industry import time")
    try:
        imported = datetime.fromisoformat(raw_time)
    except ValueError as exc:
        raise SecIndustryError("Invalid SEC industry import time") from exc
    if imported.utcoffset() is None:
        raise SecIndustryError("SEC industry import time requires timezone")
    entries = body.get("entries")
    if not isinstance(entries, dict) or not entries or len(entries) > 150_000:
        raise SecIndustryError("Invalid SEC SIC entry mapping")
    parsed: dict[str, SicEntry] = {}
    for cik, row in entries.items():
        if not isinstance(cik, str) or _CIK.fullmatch(cik) is None:
            raise SecIndustryError("Invalid pinned SEC CIK")
        if not isinstance(row, dict) or set(row) != {"sic", "description"}:
            raise SecIndustryError("Invalid pinned SEC SIC entry")
        entry = _extract_metadata({"cik": cik, "sic": row["sic"],
                                   "sicDescription": row["description"]}, cik)
        if entry is None:
            raise SecIndustryError("Invalid pinned SEC SIC entry")
        parsed[cik] = entry
    skipped = body.get("skipped_large_members")
    if isinstance(skipped, bool) or not isinstance(skipped, int) or skipped < 0:
        raise SecIndustryError("Invalid skipped-member counter")
    return SicReference(imported.astimezone(UTC), body["source_sha256"],
                        body["ticker_source_sha256"], parsed, skipped, source_kind)


def review_sec_industry(
    symbols: Sequence[str], ticker_reference: SecReference | None,
    sic_reference: SicReference | None, *, now: datetime | None = None,
) -> dict[str, Any]:
    """Review <=2 proposed tickers; fail closed if filer mapping or SIC uncertain."""
    current = now or datetime.now(UTC)
    if current.utcoffset() is None:
        raise SecIndustryError("Review time requires timezone")
    requested = list(symbols)
    if len(requested) > 2 or len(set(requested)) != len(requested):
        raise SecIndustryError("SEC SIC review expects up to two distinct symbols")
    status = "checked"
    if ticker_reference is None or sic_reference is None:
        status = "unavailable"
    elif (current < ticker_reference.imported_at_utc or
          current - ticker_reference.imported_at_utc > MAX_AGE or
          current < sic_reference.imported_at_utc or
          current - sic_reference.imported_at_utc > MAX_AGE):
        status = "stale"
    elif sic_reference.ticker_source_sha256 != ticker_reference.source_sha256:
        status = "mismatched_reference"
    approved: list[str] = []
    matches: list[dict[str, str]] = []
    excluded: list[dict[str, str]] = []
    used_sic: set[str] = set()
    for symbol in requested:
        if status != "checked":
            excluded.append({"symbol": symbol, "reason": f"industry_reference_{status}"})
            continue
        assert ticker_reference is not None and sic_reference is not None
        filers = ticker_reference.entries.get(symbol, ())
        if len(filers) != 1:
            excluded.append({"symbol": symbol, "reason": "industry_filer_missing_or_ambiguous"})
            continue
        filer = filers[0]
        entry = sic_reference.entries.get(filer.cik)
        if entry is None:
            excluded.append({"symbol": symbol, "reason": "industry_sic_unavailable"})
            continue
        matches.append({"symbol": symbol, "cik": filer.cik,
                        "sic": entry.sic, "sic_description": entry.description})
        if entry.sic in used_sic:
            excluded.append({"symbol": symbol, "reason": "same_reported_sic_as_prior_stock"})
            continue
        used_sic.add(entry.sic)
        approved.append(symbol)
    return {
        "version": VERSION,
        "status": status,
        "requested_symbols": requested,
        "approved_symbols": approved,
        "matches": matches,
        "excluded": excluded,
        "source_url": (SOURCE_URL if sic_reference.source_kind == "bulk_archive" else INDIVIDUAL_SOURCE_URL) if sic_reference else None,
        "source_sha256": sic_reference.source_sha256 if sic_reference else None,
        "imported_at_utc": sic_reference.imported_at_utc.isoformat() if sic_reference else None,
        "caveat": (
            "SEC SIC is current issuer-level business classification, NOT a verified "
            "security class, market sector mapping, segment-exposure measurement, "
            "independent diversification guarantee, or point-in-time industry record. "
            "Same SIC exclusions are deliberately conservative."
        ),
    }
