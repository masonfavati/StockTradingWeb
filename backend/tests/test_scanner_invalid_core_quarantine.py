"""Market scanner quarantines unusable securities without fabricating OHLCV."""

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.analysis.forward_record import build_forward_record, universe_digest
from app.analysis.market_scan import scan_market
from app.market_data.asset_search import SearchResult
from app.market_data.history_client import (
    AlpacaHistoryClient,
    DailyBar,
    HistoricalDataError,
    HistoryAdjustment,
    HistoryFeed,
    parse_daily_page,
)

T0 = datetime(2026, 11, 14, 20, tzinfo=UTC)
BAR = {
    "t": "2026-11-13T05:00:00Z",
    "o": Decimal(110),
    "h": Decimal(112),
    "l": Decimal(109),
    "c": Decimal(111),
    "v": 100_000,
    "n": 1_000,
    "vw": Decimal("110.5"),
}


@pytest.mark.parametrize("invalid", [0, -1, "NaN", "broken", None, False, []])
def test_strict_parser_still_rejects_bad_open(invalid: object) -> None:
    with pytest.raises(HistoricalDataError, match="Invalid open"):
        parse_daily_page({"bars": {"ABC": [{**BAR, "o": invalid}]}}, ["ABC"])


def test_screening_parser_tracks_bad_core_and_retains_other_symbols() -> None:
    errors: list[tuple[str, date | None, str]] = []
    bars = parse_daily_page(
        {"bars": {"ABC": [{**BAR, "o": 0}], "DEF": [BAR]}},
        ["ABC", "DEF"],
        on_invalid_core=lambda symbol, day, problem: errors.append((symbol, day, problem)),
    )
    assert [bar.symbol for bar in bars] == ["DEF"]
    assert errors == [("ABC", date(2026, 11, 13), "Invalid open value in provider data.")]


def test_inconsistent_ohlc_not_silently_accepted() -> None:
    errors: list[str] = []
    bars = parse_daily_page(
        {"bars": {"ABC": [{**BAR, "h": 30}]}},
        ["ABC"],
        on_invalid_core=lambda _symbol, _day, problem: errors.append(problem),
    )
    assert bars == []
    assert errors == ["Inconsistent OHLC prices in historical data."]


def test_structural_corruption_always_fails() -> None:
    on_error = lambda _symbol, _day, _reason: None
    with pytest.raises(HistoricalDataError, match="Unexpected symbol"):
        parse_daily_page({"bars": {"UNEXPECTED": [BAR]}}, ["ABC"], on_invalid_core=on_error)
    with pytest.raises(HistoricalDataError, match="unexpected bars"):
        parse_daily_page({"wrong": {}}, ["ABC"], on_invalid_core=on_error)
    with pytest.raises(HistoricalDataError, match="Invalid daily-bar"):
        parse_daily_page({"bars": {"ABC": ["not a row"]}}, ["ABC"], on_invalid_core=on_error)


def test_official_client_screening_is_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    client = object.__new__(AlpacaHistoryClient)
    monkeypatch.setattr(client, "_get_page", lambda _params: {
        "bars": {"ABC": [{**BAR, "o": 0}], "DEF": [BAR]},
        "next_page_token": None,
    })
    errors: list[str] = []
    result = list(client.screening_pages(
        ["ABC", "DEF"], start=date(2026, 11, 1), end=date(2026, 11, 14),
        feed="sip", adjustment="all", page_limit=10000,
        on_invalid_core=lambda symbol, _day, _reason: errors.append(symbol),
    ))
    assert len(result) == 1
    assert [bar.symbol for bar in result[0]] == ["DEF"]
    assert errors == ["ABC"]
    with pytest.raises(HistoricalDataError, match="Invalid open"):
        list(client.pages(
            ["ABC", "DEF"], start=date(2026, 11, 1), end=date(2026, 11, 14),
            feed="sip", adjustment="all", page_limit=10000,
        ))


def series(symbol: str) -> list[DailyBar]:
    bars: list[DailyBar] = []
    for day in range(65):
        price = Decimal(100 + day)
        timestamp = datetime(2026, 8, 1, tzinfo=UTC) + timedelta(days=day)
        bars.append(DailyBar(
            symbol=symbol, session_date=timestamp.date(), bar_timestamp=timestamp,
            open_price=price, high_price=price + 1, low_price=price - 1,
            close_price=price, volume=300_000, trade_count=1_000, vwap=price,
        ))
    return bars


class Directory:
    def list_active(self) -> list[SearchResult]:
        return [SearchResult("ABC", "Company ABC", True), SearchResult("DEF", "Company DEF", True)]


class ScannerHistory:
    def screening_pages(
        self,
        symbols: Sequence[str],
        *,
        start: date,
        end: date | datetime,
        feed: HistoryFeed,
        adjustment: HistoryAdjustment,
        page_limit: int,
        on_invalid_core,
    ) -> Iterator[list[DailyBar]]:
        del start, end, page_limit
        assert feed == "sip"
        assert adjustment == "all"
        assert sorted(symbols) == ["ABC", "DEF"]
        # An unusable ABC record in any later page disqualifies ALL ABC history.
        yield series("ABC") + series("DEF")
        on_invalid_core("ABC", date(2026, 9, 12), "Invalid open value in provider data.")
        yield []

    def pages(self, *args: object, **kwargs: object) -> Iterator[list[DailyBar]]:
        raise AssertionError("Screening client should use screening_pages")
        yield []


def test_bad_symbol_never_enters_shortlist_even_after_good_pages() -> None:
    progress: list[tuple[int, int]] = []
    result = scan_market(
        Directory(), ScannerHistory(),  # type: ignore[arg-type]
        now=T0,
        progress=lambda done, total: progress.append((done, total)),
    )
    assert result.processed == result.considered == 2
    assert result.excluded_invalid_core_symbols == 1
    assert result.invalid_core_records == 1
    assert "ABC" in result.invalid_core_examples[0]
    assert all(item.symbol != "ABC" for item in result.candidates)
    assert progress == [(2, 2)]


def test_forward_record_discloses_core_data_exclusions() -> None:
    checkpoint = build_forward_record(
        started_at=T0, finished_at=T0 + timedelta(seconds=20),
        latest_completed_session=date(2026, 11, 13),
        latest_scan_session=date(2026, 11, 13),
        directory_size=2, considered=2, processed=2, qualified=0,
        symbol_digest=universe_digest(["ABC", "DEF"]),
        candidates=[], horizon=20,
        excluded_invalid_core_symbols=1,
        invalid_core_records=1,
        invalid_core_examples=["ABC 2026-11-13: Invalid open value in provider data."],
    )
    assert checkpoint["excluded_due_to_invalid_core_bars"] == 1
    assert checkpoint["invalid_core_bar_records"] == 1
    assert "ABC" in checkpoint["invalid_core_examples"][0]
    assert any("excluded" in warning for warning in checkpoint["warnings"])


def test_forward_record_refuses_inconsistent_quality_counts() -> None:
    base = {
        "started_at": T0,
        "finished_at": T0 + timedelta(seconds=20),
        "latest_completed_session": date(2026, 11, 13),
        "latest_scan_session": date(2026, 11, 13),
        "directory_size": 2,
        "considered": 2,
        "processed": 2,
        "qualified": 0,
        "symbol_digest": universe_digest(["ABC", "DEF"]),
        "candidates": [],
        "horizon": 20,
    }
    with pytest.raises(ValueError, match="exclusion"):
        build_forward_record(**base, excluded_invalid_core_symbols=1, invalid_core_records=0)
    with pytest.raises(ValueError, match="exclusion"):
        build_forward_record(**base, excluded_invalid_core_symbols=-1, invalid_core_records=1)
