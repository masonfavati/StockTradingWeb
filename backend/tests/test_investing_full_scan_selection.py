"""Investment candidates must not be hidden by the scanner's public top 20."""

from datetime import UTC, date, datetime

import pytest

from app.analysis.market_scan import ScanResults, investment_shortlist
from app.analysis.opportunities import ResearchCandidate, shortlist
from app.api.scanner import ScanManager

SESSION = date(2026, 11, 13)


def candidate(
    symbol: str, *, score: float, name: str | None = None,
    price: float = 25.0, dollar_volume: float = 12_000_000.0,
) -> ResearchCandidate:
    return ResearchCandidate(
        symbol=symbol,
        name=name or f"{symbol} Incorporated Common Stock",
        last_session=SESSION,
        adjusted_close=price,
        return_20d_pct=10.0,
        return_60d_pct=20.0,
        annualized_volatility_pct=40.0,
        drawdown_60d_pct=-8.0,
        approx_daily_dollar_volume=dollar_volume,
        research_score=score,
    )


def test_investment_shortlist_considers_all_not_only_public_top_twenty() -> None:
    # The 20 highest-scoring research entries are warrant securities; none
    # has evidence for a common-share allocation. A lower-ranked common stock
    # *must* remain discoverable rather than being hidden by the top-20 cut.
    unverified = [
        candidate(f"W{index:02d}", score=100.0 - index, name=f"W{index:02d} Warrant")
        for index in range(20)
    ]
    suitable = candidate("GOOD", score=1.0)
    all_candidates = [*unverified, suitable]
    assert suitable not in shortlist(all_candidates)

    investment_picks, audit = investment_shortlist(all_candidates, SESSION.isoformat())
    assert [row.symbol for row in investment_picks] == ["GOOD"]
    assert audit["screened_count"] == 21
    assert audit["excluded_counts"]["unverified_share_type"] == 20
    assert audit["selected_count"] == 1


def test_investment_shortlist_preserves_liquidity_security_and_session_gates() -> None:
    bad = candidate("LOW", score=10, dollar_volume=2_000_000.0)
    old = candidate("OLD", score=9)
    good = candidate("GOOD", score=8)
    result, report = investment_shortlist(
        [bad, old, good], SESSION.isoformat(),
    )
    assert [row.symbol for row in result] == ["OLD", "GOOD"]
    assert report["excluded_counts"]["below_liquidity_screen"] == 1
    no_recent, review = investment_shortlist([good], "2026-11-12")
    assert no_recent == []
    assert review["excluded_counts"]["outdated_session"] == 1


def test_scanner_publishes_independent_investment_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    from app.api import scanner

    raw = [candidate("WARRANT", score=10, name="Warrant Securities")]
    reviewed = [candidate("GOOD", score=1)]
    scan = ScanResults(
        directory_size=2, considered=2, processed=2, qualified=2,
        latest_session=SESSION.isoformat(), candidates=raw,
        investing_candidates=reviewed,
        investing_quality_review={
            "screened_count": 2,
            "selected_count": 1,
            "excluded_counts": {"unverified_share_type": 1},
        },
    )
    monkeypatch.setattr(scanner, "get_asset_catalog", lambda: object())
    monkeypatch.setattr(scanner, "AlpacaHistoryClient", lambda _settings: object())
    monkeypatch.setattr(scanner, "Settings", lambda: object())
    monkeypatch.setattr(scanner, "scan_market", lambda *_args, **_kwargs: scan)

    manager = ScanManager()
    assert manager.begin(now=datetime.now(UTC))
    manager.execute()
    snapshot = manager.snapshot()
    assert snapshot.state == "complete"
    assert [row["symbol"] for row in snapshot.candidates] == ["WARRANT"]
    assert [row["symbol"] for row in snapshot.investing_candidates] == ["GOOD"]
    assert snapshot.investing_quality_review["screened_count"] == 2


def test_scan_manager_clears_investing_pool_on_new_run() -> None:
    manager = ScanManager()
    assert manager.begin(now=datetime.now(UTC))
    snapshot = manager.snapshot()
    assert snapshot.investing_candidates == []
    assert snapshot.investing_quality_review == {}


def test_investing_route_uses_vetted_full_market_pool(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    from datetime import timedelta
    from types import SimpleNamespace

    from app.api import investing

    now = datetime.now(UTC)
    session = (now - timedelta(days=1)).date().isoformat()

    def record(symbol: str, name: str) -> dict[str, object]:
        return {
            "symbol": symbol,
            "name": name,
            "last_session": session,
            "adjusted_close": 25.0,
            "annualized_volatility_pct": 40.0,
            "drawdown_60d_pct": -8.0,
            "approx_daily_dollar_volume": 12_000_000.0,
        }

    snapshot = SimpleNamespace(
        state="complete",
        completed_at=now.isoformat(),
        latest_session=session,
        candidates=[record("BAD", "BAD Warrants")],
        investing_candidates=[record("GOOD", "GOOD Incorporated Common Stock")],
    )
    monkeypatch.setattr(investing, "_MANAGER", SimpleNamespace(snapshot=lambda: snapshot))
    monkeypatch.setattr(
        investing, "_latest_saved_checkpoint",
        lambda _root: pytest.fail("Do not consult saved research if current pool is vetted"),
    )
    selected, details = investing._research_candidates()
    assert [item["symbol"] for item in selected] == ["GOOD"]
    assert details["source"] == "latest_full_market_scan"


def test_quality_screened_pool_is_broader_but_explicitly_bounded() -> None:
    candidates = [candidate(f"GOOD{i:02d}", score=float(100 - i)) for i in range(30)]
    result, audit = investment_shortlist(candidates, SESSION.isoformat())
    assert len(result) == 20
    assert audit["screened_count"] == 30
    assert audit["selected_count"] == 20
