"""End-to-end request wiring without network access or simulated trade execution."""

import math
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi import HTTPException

from app.analysis.historical_growth import PricePoint
from app.analysis.investing_service import InvestingDataError
from app.api import investing


def sample_prices(multiplier: float) -> list[PricePoint]:
    start = date.today() - timedelta(days=1301)
    return [PricePoint(start + timedelta(days=i),
                       100 * (1.0001 ** i) * (1 + 0.03 * math.sin(i * multiplier)))
            for i in range(1300)]


def test_manual_ticker_forecast_does_not_start_a_market_scan(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(investing, '_history', lambda *args, **kwargs: {
        'AAA': sample_prices(0.1), 'SPY': sample_prices(0.06),
    })
    # If the user supplied a particular ticker, the broad market scanner must
    # not be consulted or billed in the background.
    monkeypatch.setattr(investing, '_research_candidates', lambda: 1 / 0)
    result = investing.growth_plan(investing.GrowthPlanRequest(
        budget_usd=Decimal(100), symbols=['AAA'], horizon='long',
    ))
    assert result['selection']['source'] == 'user_selected_tickers_not_entire_market'
    # The actual historical-analogue SPY forecast can be negative even when
    # synthetic prices drift upward. Do not force a risky allocation anyway.
    spy_change = result['benchmark']['estimated_change_pct']
    expected_core = '55.00' if spy_change > 0 else '0.00'
    expected_cash = '45.00' if spy_change > 0 else '100.00'
    assert result['plan']['invested_usd'] == expected_core
    assert result['plan']['cash_usd'] == expected_cash
    assert not any(row['category'] == 'experimental_stock'
                   for row in result['plan']['allocation'])
    assert result['plan']['current_model_status'] == 'historical_backtest_only_not_prospectively_validated'


def test_missing_market_research_does_not_invent_a_full_market_rank(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_data() -> None:
        raise InvestingDataError('No fresh full-market shortlist is available.')
    monkeypatch.setattr(investing, '_research_candidates', no_data)
    monkeypatch.setattr(investing, '_MANAGER', SimpleNamespace(
        snapshot=lambda: SimpleNamespace(state='idle', latest_session=None),
    ))
    with pytest.raises(HTTPException) as error:
        investing.growth_plan(investing.GrowthPlanRequest(budget_usd=Decimal(100)))
    assert error.value.status_code == 409


def test_manual_purchase_persists_and_can_be_undone(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(investing, '_research_root', lambda: tmp_path)
    trade = investing.log_trade(investing.ManualTradeRequest(
        action='buy', symbol='AAA', date=date(2026, 11, 10),
        shares=Decimal(2), price_usd=Decimal(10),
    ))
    assert trade['saved'] is True
    summary = investing.manual_portfolio()
    assert summary['summary']['holdings'][0]['shares'] == '2'
    assert investing.undo_trade(trade['trade']['id'])['removed'] is True
    assert investing.manual_portfolio()['summary']['holdings'] == []


def test_completed_market_scan_with_no_eligible_stocks_still_produces_truthful_budget(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No verified stock shortlist may become a core-and-cash plan, never stock picks."""
    def no_shortlist() -> None:
        raise InvestingDataError(
            'No fresh full-market shortlist is available. A new market search is needed.'
        )

    monkeypatch.setattr(investing, '_research_candidates', no_shortlist)
    monkeypatch.setattr(investing, '_MANAGER', SimpleNamespace(
        snapshot=lambda: SimpleNamespace(state='complete', latest_session='2026-11-13'),
    ))
    history_calls: list[list[str]] = []

    def market_history(symbols: list[str], **_kwargs: object) -> dict[str, list[PricePoint]]:
        history_calls.append(symbols)
        return {'SPY': sample_prices(0.06)}

    monkeypatch.setattr(investing, '_history', market_history)
    result = investing.growth_plan(investing.GrowthPlanRequest(
        budget_usd=Decimal(2500), horizon='long', style='balanced',
        allow_exploratory=True,
    ))
    assert history_calls == [['SPY']]
    assert result['selection']['source'] == 'completed_scan_no_verified_shortlist'
    assert 'no current individual-stock shortlist' in result['selection']['note']
    assert result['ranked_stocks'] == []
    assert result['preview_history'] == {}
    assert result['plan']['exploratory'] is False
    spy_change = result['benchmark']['estimated_change_pct']
    if spy_change > 0:
        assert result['plan']['invested_usd'] == '1375.00'
        assert result['plan']['cash_usd'] == '1125.00'
        assert {row['category'] for row in result['plan']['allocation']} == {'diversified_core', 'cash'}
    else:
        # Non-positive SPY estimates must NOT be turned into an automatic
        # 55% investment. A completed scan can legitimately leave 100% cash.
        assert result['plan']['invested_usd'] == '0.00'
        assert result['plan']['cash_usd'] == '2500.00'
        assert {row['category'] for row in result['plan']['allocation']} == {'cash'}
        assert any(row['symbol'] == 'SPY' for row in result['plan']['declined'])
    assert result['benchmark']['symbol'] == 'SPY'


def test_failed_market_scan_does_not_fabricate_success(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def no_shortlist() -> None:
        raise InvestingDataError('No fresh full-market shortlist is available.')

    monkeypatch.setattr(investing, '_research_candidates', no_shortlist)
    monkeypatch.setattr(investing, '_MANAGER', SimpleNamespace(
        snapshot=lambda: SimpleNamespace(state='failed', latest_session=None),
    ))
    monkeypatch.setattr(investing, '_history', lambda *_args, **_kwargs: 1 / 0)
    with pytest.raises(HTTPException) as error:
        investing.growth_plan(investing.GrowthPlanRequest(budget_usd=Decimal(100)))
    assert error.value.status_code == 409


def test_growth_ranking_reports_limited_forecast_coverage(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """A completed universe scan must not be advertised as an all-stock forecast."""
    session = (date.today() - timedelta(days=1)).isoformat()
    monkeypatch.setattr(investing, '_research_candidates', lambda: (
        [{'symbol': 'MKTX'}], {'source': 'latest_full_market_scan', 'session': session},
    ))
    monkeypatch.setattr(investing, '_MANAGER', SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            state='complete', latest_session=session, processed=8000,
            investing_quality_review={'screened_count': 700},
        ),
    ))
    monkeypatch.setattr(investing, '_history', lambda *_args, **_kwargs: {
        'MKTX': sample_prices(0.1), 'SPY': sample_prices(0.06),
    })
    result = investing.growth_plan(investing.GrowthPlanRequest(
        budget_usd=Decimal(100), horizon='long', allow_exploratory=True,
    ))
    scope = result['ranking_scope']
    assert scope['complete_market_forecast'] is False
    assert scope['market_symbols_screened'] == 8000
    assert scope['preliminary_candidates_quality_screened'] == 700
    assert scope['symbols_selected_for_forecast'] == 1
    assert scope['symbols_with_estimates'] == len(result['ranked_stocks'])
    assert scope['symbols_with_estimates'] <= 1
    assert 'NOT every stock' in result['important']


def test_comparison_uses_one_history_request_and_refuses_unscreened_stock_allocations(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def local_prices(symbols: list[str], **_kwargs: object) -> dict[str, list[PricePoint]]:
        calls.append(symbols)
        return {"AAA": sample_prices(0.13), "SPY": sample_prices(0.06)}

    monkeypatch.setattr(investing, "_history", local_prices)
    monkeypatch.setattr(investing, "_research_candidates", lambda: 1 / 0)
    result = investing.growth_plan(investing.GrowthPlanRequest(
        budget_usd=Decimal(2500), symbols=["AAA"], horizon="long",
        allow_exploratory=True,
    ))
    assert calls == [["AAA", "SPY"]]
    assert [row["id"] for row in result["scenario_comparison"]["approaches"]] == [
        "combined", "core_only", "max_model_change",
    ]
    assert result["scenario_comparison"]["approaches"][2]["available"] is False
    assert all(row["category"] != "experimental_stock"
               for option in result["scenario_comparison"]["approaches"]
               for row in option["allocation"])


def test_verified_scan_reuses_same_histories_for_all_comparisons(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[list[str]] = []

    def local_prices(symbols: list[str], **_kwargs: object) -> dict[str, list[PricePoint]]:
        calls.append(symbols)
        return {"AAA": sample_prices(0.13), "BBB": sample_prices(0.21),
                "SPY": sample_prices(0.06)}

    monkeypatch.setattr(investing, "_history", local_prices)
    monkeypatch.setattr(investing, "_research_candidates", lambda: (
        [{"symbol": "AAA"}, {"symbol": "BBB"}],
        {"source": "latest_full_market_scan", "session": "2026-11-13"},
    ))
    monkeypatch.setattr(investing, "_MANAGER", SimpleNamespace(
        snapshot=lambda: SimpleNamespace(
            state="complete", latest_session="2026-11-13", processed=500,
            investing_quality_review={},
        ),
    ))
    result = investing.growth_plan(investing.GrowthPlanRequest(
        budget_usd=Decimal(2500), horizon="long", allow_exploratory=True,
    ))
    assert calls == [["AAA", "BBB", "SPY"]]
    assert result["scenario_comparison"]["approaches"][2]["available"] is True
    for option in result["scenario_comparison"]["approaches"]:
        assert Decimal(option["invested_usd"]) + Decimal(option["cash_usd"]) == Decimal(2500)
        if option["id"] == "max_model_change":
            assert option["combinations_considered"] is not None
            assert option["winning_structure"] in (
                "spy_and_stocks", "stocks_and_cash", "spy_only", "cash_only",
            )
