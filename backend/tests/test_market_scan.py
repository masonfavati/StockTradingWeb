"""Full-universe scanner does not accidentally use the saved watchlist."""

from collections.abc import Iterator, Sequence
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal

import pytest

from app.analysis.market_scan import scan_market
from app.market_data.asset_search import SearchResult
from app.market_data.history_client import DailyBar, HistoryAdjustment, HistoryFeed


def series(symbol: str) -> list[DailyBar]:
    result = []
    for index in range(70):
        price = Decimal(100 + index * 2 + index % 3)
        result.append(DailyBar(
            symbol=symbol,
            session_date=date(2026, 7, 1) + timedelta(days=index),
            bar_timestamp=datetime(2026, 7, 1, tzinfo=UTC) + timedelta(days=index),
            open_price=price,
            high_price=price + 1,
            low_price=price - 1,
            close_price=price,
            volume=300000,
            trade_count=100,
            vwap=price,
        ))
    return result


class Directory:
    def list_active(self) -> list[SearchResult]:
        return [
            SearchResult("AAA", "A Incorporated", True),
            SearchResult("BBB", "B Incorporated", True),
            SearchResult("UNTRADABLE", "Not Tradable", False),
        ]


class History:
    def __init__(self) -> None:
        self.seen: list[str] = []

    def pages(
        self,
        symbols: Sequence[str],
        *,
        start: date,
        end: date | datetime,
        feed: HistoryFeed,
        adjustment: HistoryAdjustment,
        page_limit: int,
    ) -> Iterator[list[DailyBar]]:
        assert feed == "sip"
        assert adjustment == "all"
        assert page_limit == 10000
        self.seen.extend(symbols)
        yield [bar for symbol in symbols for bar in series(symbol)]


def test_scans_all_eligible_assets_and_reports_coverage() -> None:
    history = History()
    progress: list[tuple[int, int]] = []
    result = scan_market(
        Directory(), history,
        now=datetime(2026, 9, 15, tzinfo=UTC),
        progress=lambda seen, total: progress.append((seen, total)),
    )
    assert history.seen == ["AAA", "BBB"]
    assert result.directory_size == 3
    assert result.considered == 2
    assert result.processed == 2
    assert result.qualified == 2
    assert progress == [(2, 2)]
    assert {candidate.symbol for candidate in result.candidates} == {"AAA", "BBB"}


def test_provider_failure_is_not_reported_as_partial_success() -> None:
    class BrokenHistory(History):
        def pages(self, *args: object, **kwargs: object) -> Iterator[list[DailyBar]]:
            raise RuntimeError("upstream unavailable")
            yield []

    with pytest.raises(RuntimeError, match="upstream"):
        scan_market(
            Directory(), BrokenHistory(),  # type: ignore[arg-type]
            now=datetime(2026, 9, 15, tzinfo=UTC),
            progress=lambda _a, _b: None,
        )
