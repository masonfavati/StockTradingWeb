"""Conservative, read-only name screening and safe offset guards."""

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime
from uuid import UUID

import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.db.base import Base
from app.market_data.security_profiles import (
    ClassifiedAsset,
    choose_profile_symbols,
    classify_security,
    profile_fingerprint,
    profile_includes,
)
from app.market_data.universe_history import (
    AssetRecord,
    backfill_universe,
    capture_universe,
    eligible_symbols,
    show_profiles,
)

DAY = date(2026, 11, 14)
NOW = datetime(2026, 11, 14, 21, tzinfo=UTC)
START = date(2026, 8, 1)


@pytest.mark.parametrize(
    ("symbol", "name", "expected"),
    [
        ("AAPL", "Apple Inc. Common Stock", "common_name_evidence"),
        ("MSFT", "Microsoft Corporation Common Shares", "common_name_evidence"),
        ("X", "Ordinary Shares", "common_name_evidence"),
        ("AACIW", "Ares Acquisition Corp II Warrants", "warrant_or_right"),
        ("AAC.WS", "Ares Acquisition Corp II", "warrant_or_right"),
        ("XYZ", "Share Purchase Rights", "warrant_or_right"),
        ("AAC.U", "Acquisition Co. Units", "unit"),
        ("AACU", "Acquisition Co Units", "unit"),
        ("PRF", "7% Series A Preferred Stock", "preferred"),
        ("SPY", "SPDR S&P 500 ETF", "fund_or_etp"),
        ("QQQ", "Nasdaq 100 Exchange-Traded Fund", "fund_or_etp"),
        ("ADS", "Company Sponsored ADR", "depositary"),
        ("APLE", "Apple Hospitality REIT", "unclassified"),
        ("BRK.B", "Berkshire Hathaway Class B", "unclassified"),
        ("ABC", "", "missing_name"),
        ("W", "Wayfair Inc.", "unclassified"),
        ("SUM", "Community Bancorp Common Stock", "common_name_evidence"),
        ("XYZ", "Rightside Holdings Common Stock", "common_name_evidence"),
    ],
)
def test_heuristic_labels_are_conservative(symbol: str, name: str, expected: str) -> None:
    assert classify_security(symbol, name) == expected


def test_profile_inclusion_never_claims_bare_name_is_certified_common() -> None:
    assert profile_includes("common_name_evidence", "common-name-evidence")
    assert not profile_includes("unclassified", "common-name-evidence")
    assert profile_includes("unclassified", "exclude-obvious-complex")
    assert not profile_includes("fund_or_etp", "exclude-obvious-complex")
    assert profile_includes("fund_or_etp", "all")
    with pytest.raises(ValueError):
        profile_includes("unclassified", "invalid-profile")  # type: ignore[arg-type]


def test_filter_preserves_original_all_offsets_and_avoids_ambiguous_tickers() -> None:
    rows = [
        ClassifiedAsset("AAC", "Company Common Stock", "common_name_evidence"),
        ClassifiedAsset("AAC.WS", "Company Warrants", "warrant_or_right"),
        ClassifiedAsset("MSFT", "Microsoft Common Stock", "common_name_evidence"),
        ClassifiedAsset("W", "Wayfair", "unclassified"),
        ClassifiedAsset("AAC", "Other Company Common Stock", "common_name_evidence"),
        ClassifiedAsset("SPY", "SPY ETF", "fund_or_etp"),
    ]
    assert choose_profile_symbols(rows, profile="all") == ["AAC", "AAC.WS", "MSFT", "SPY", "W"]
    assert choose_profile_symbols(rows, profile="common-name-evidence") == ["MSFT"]
    assert choose_profile_symbols(rows, profile="exclude-obvious-complex") == ["MSFT", "W"]


def test_fingerprint_depends_on_date_profile_and_order() -> None:
    a = profile_fingerprint(captured_on=DAY, profile="all", symbols=["AAA", "ABC"])
    assert len(a) == 16
    assert a == profile_fingerprint(captured_on=DAY, profile="all", symbols=["AAA", "ABC"])
    assert a != profile_fingerprint(captured_on=DAY, profile="all", symbols=["ABC", "AAA"])
    assert a != profile_fingerprint(captured_on=DAY, profile="common-name-evidence", symbols=["AAA", "ABC"])
    assert a != profile_fingerprint(captured_on=date(2026, 11, 13), profile="all", symbols=["AAA", "ABC"])


class Directory:
    def list_assets(self) -> list[AssetRecord]:
        return [
            AssetRecord(str(UUID(int=1)), "AAA", "AAA Inc. Common Stock", "NASDAQ", "active", True),
            AssetRecord(str(UUID(int=2)), "AAA.WS", "AAA Inc. Warrants", "NASDAQ", "active", True),
            AssetRecord(str(UUID(int=3)), "BBB", "BBB Holdings", "NYSE", "active", True),
            AssetRecord(str(UUID(int=4)), "CCC", "", "NASDAQ", "active", True),
            AssetRecord(str(UUID(int=5)), "DDD", "DDD Common Stock", "NYSE", "inactive", False),
        ]


class NoRequests:
    def __init__(self) -> None:
        self.calls = 0

    def pages(
        self, symbols: Sequence[str], *, start: date, end: date | datetime,
        feed: str, adjustment: str,
    ) -> Iterator[list[object]]:
        self.calls += 1
        yield []


@pytest.fixture
def db() -> Iterator[Session]:
    engine = create_engine("sqlite+pysqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    engine.dispose()


def test_profiles_read_existing_snapshot_and_preserve_legacy_order(
    db: Session, capsys: pytest.CaptureFixture[str]
) -> None:
    capture_universe(db, Directory(), observed_at=NOW)
    assert eligible_symbols(db, DAY) == ["AAA", "AAA.WS", "BBB", "CCC"]
    assert eligible_symbols(db, DAY, profile="all") == ["AAA", "AAA.WS", "BBB", "CCC"]
    assert eligible_symbols(db, DAY, profile="exclude-obvious-complex") == ["AAA", "BBB"]
    assert eligible_symbols(db, DAY, profile="common-name-evidence") == ["AAA"]
    show_profiles(db, DAY)
    printed = capsys.readouterr().out
    assert "profile=all: 4 symbols; fingerprint=" in printed
    assert "profile=common-name-evidence: 1 symbols; fingerprint=" in printed
    assert "NOT verified common shares" in printed
    assert "warrant_or_right: 1; examples: AAA.WS" in printed


def test_mismatching_fingerprint_aborts_before_request(db: Session) -> None:
    capture_universe(db, Directory(), observed_at=NOW)
    provider = NoRequests()
    with pytest.raises(ValueError, match="fingerprint mismatch"):
        backfill_universe(
            db, provider, captured_on=DAY, start=START, now=NOW,
            offset=0, limit=2, batch_size=2, profile="all",
            expected_fingerprint="bad-fingerprint",
        )
    assert provider.calls == 0


def test_profile_backfill_never_uses_all_profile_offsets(db: Session) -> None:
    capture_universe(db, Directory(), observed_at=NOW)
    provider = NoRequests()
    total, selected, pages, rows = backfill_universe(
        db, provider, captured_on=DAY, start=START, now=NOW,
        offset=0, limit=2, batch_size=2, profile="exclude-obvious-complex",
    )
    assert (total, selected, pages, rows) == (2, 2, 1, 0)
    assert provider.calls == 1


def test_profiles_fail_cleanly_without_snapshot(db: Session) -> None:
    with pytest.raises(ValueError, match="No saved universe snapshot"):
        show_profiles(db, DAY)
