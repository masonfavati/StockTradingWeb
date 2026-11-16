"""Broader forecast coverage must preserve existing Alpaca request bounds."""

from collections.abc import Sequence

import pytest

from app.api import investing


def test_20_stock_forecast_download_in_safe_chunks(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_history(symbols: list[str], *, adjustment: str) -> dict[str, Sequence[object]]:
        assert adjustment == "all"
        assert len(symbols) <= 12
        calls.append(symbols)
        return {symbol: [] for symbol in symbols}

    monkeypatch.setattr(investing, "_history", fake_history)
    selected = [f"A{i:02d}" for i in range(20)]
    returned = investing._planning_histories(selected)
    assert len(calls) == 2
    assert calls[0][-1] == "SPY"
    assert all("SPY" not in batch for batch in calls[1:])
    assert set(returned) == {"SPY", *selected}


def test_small_forecast_still_makes_one_provider_call(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[list[str]] = []

    def fake_history(symbols: list[str], *, adjustment: str) -> dict:
        assert adjustment == "all"
        calls.append(symbols)
        return {}

    monkeypatch.setattr(investing, "_history", fake_history)
    investing._planning_histories(["AAA", "BBB"])
    assert calls == [["AAA", "BBB", "SPY"]]
