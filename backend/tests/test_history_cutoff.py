from datetime import UTC, date, datetime, timedelta

import pytest

from app.market_data.history_client import AlpacaHistoryClient
from app.market_data.history_import import completed_session_cutoff


def test_sip_cutoff_is_prior_completed_ny_day() -> None:
    # Saturday after Friday's market close, in Eastern Standard Time.
    now = datetime(2026, 11, 14, 18, 0, tzinfo=UTC)
    cutoff = completed_session_cutoff(now=now)
    assert cutoff == datetime(2026, 11, 14, 4, 0, tzinfo=UTC)
    assert now - cutoff > timedelta(minutes=15)


def test_sip_cutoff_is_safe_just_after_ny_midnight() -> None:
    # Saturday 00:01 EST still gives a cutoff over an hour old.
    now = datetime(2026, 11, 14, 5, 1, tzinfo=UTC)
    cutoff = completed_session_cutoff(now=now)
    assert now - cutoff == timedelta(minutes=61)


def test_sip_cutoff_respects_daylight_saving_time() -> None:
    # July is on Eastern Daylight Time: previous day 23:00 is 03:00 UTC.
    now = datetime(2026, 7, 7, 16, 0, tzinfo=UTC)
    cutoff = completed_session_cutoff(now=now)
    assert cutoff == datetime(2026, 7, 7, 3, 0, tzinfo=UTC)


def test_history_client_sends_explicit_utc_timestamp(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    client = object.__new__(AlpacaHistoryClient)
    requests: list[dict[str, str]] = []

    def fake_get_page(params: dict[str, str]) -> dict[str, object]:
        requests.append(dict(params))
        return {"bars": {}, "next_page_token": None}

    monkeypatch.setattr(client, "_get_page", fake_get_page)
    list(client.pages(
        ["AAPL"],
        start=date(2022, 1, 1),
        end=datetime(2026, 11, 14, 4, 0, tzinfo=UTC),
    ))
    assert requests[0]["end"] == "2026-11-14T04:00:00Z"
    assert requests[0]["feed"] == "sip"


def test_history_client_rejects_naive_end_timestamp() -> None:
    client = object.__new__(AlpacaHistoryClient)
    with pytest.raises(ValueError, match="time zone"):
        list(client.pages(
            ["AAPL"],
            start=date(2022, 1, 1),
            end=datetime(2026, 11, 14, 4, 0),
        ))
