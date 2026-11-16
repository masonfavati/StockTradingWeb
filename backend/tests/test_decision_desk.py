"""Read-only decision explanations never substitute for prospective investment validation."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from zoneinfo import ZoneInfo

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.analysis.decision_desk import build_decision_desk
from app.api import research_dashboard as research

NOW = datetime(2026, 11, 15, 15, tzinfo=UTC)
SESSION = "2026-11-13"


def candidate(symbol: str, *, price: float = 25.0, name: str | None = None) -> dict:
    return {
        "symbol": symbol, "name": name or f"{symbol} Corporation Common Stock",
        "last_session": SESSION, "adjusted_close": price,
        "return_20d_pct": 5.5, "return_60d_pct": 12.0,
        "annualized_volatility_pct": 35.0, "drawdown_60d_pct": -10.0,
        "approx_daily_dollar_volume": 10_000_000,
        "research_score": 0.75,
    }


def make_report(*, candidates: list[dict] | None = None, time: datetime = NOW) -> dict:
    return build_decision_desk(
        source_kind="frozen_checkpoint", signal_session=SESSION,
        recorded_at_utc=time.isoformat(),
        candidates=candidates if candidates is not None else [candidate("AAA")],
        now=NOW, prediction_status="insufficient_evidence",
    )


def client() -> TestClient:
    app = FastAPI()
    app.include_router(research.router)
    return TestClient(app)


def test_empty_source_does_not_invent_stocks_or_returns() -> None:
    report = build_decision_desk(
        source_kind=None, signal_session=None, recorded_at_utc=None,
        candidates=[], now=NOW,
    )
    assert report["candidates"] == []
    assert report["quality_passed_count"] == 0
    assert report["source_recent"] is False
    assert report["prediction_status"] == "unavailable"


def test_passing_quality_screen_is_not_called_prediction() -> None:
    report = make_report()
    assert report["quality_passed_count"] == 1
    row = report["candidates"][0]
    assert row["quality_passed"] is True
    assert row["sec_filer"]["status"] == "sec_reference_unavailable"
    assert row["sec_industry"]["status"] == "industry_reference_unavailable"
    assert report["prediction_status"] == "insufficient_evidence"
    assert any("not an expected return" in caveat for caveat in report["caveats"])


def test_individual_rejection_reason_is_explained() -> None:
    report = make_report(candidates=[candidate("AAA", price=2.0)])
    assert report["candidates"][0]["quality_reason"] == "below_price_floor"
    assert report["quality_passed_count"] == 0


def test_apparent_duplicate_issuer_is_not_doubly_counted() -> None:
    report = make_report(candidates=[
        candidate("AAA", name="Alpha Class A Common Stock"),
        candidate("AAB", name="Alpha Class B Common Stock"),
    ])
    assert report["quality_passed_count"] == 1
    assert report["candidates"][1]["quality_reason"] == "repeated_apparent_issuer_or_ticker"


def test_stale_and_future_timestamps_not_recent() -> None:
    assert not make_report(time=NOW - timedelta(days=10))["source_recent"]
    assert not make_report(time=NOW + timedelta(hours=1))["source_recent"]
    assert make_report()["source_recent"]


def test_missing_invalid_metrics_are_null_not_nan() -> None:
    row = candidate("AAA")
    row["research_score"] = float("nan")
    row["adjusted_close"] = float("inf")
    report = make_report(candidates=[row])
    assert report["candidates"][0]["metrics"]["research_score"] is None
    assert report["candidates"][0]["metrics"]["adjusted_close"] is None
    assert report["candidates"][0]["quality_passed"] is False


def test_limits_visible_results_to_twenty_and_reports_total() -> None:
    report = make_report(candidates=[candidate(f"AA{chr(65 + i)}") for i in range(30)])
    assert report["displayed_count"] == 20
    assert report["considered_count"] == 30
    assert len(report["candidates"]) == 20


def test_bad_current_time_is_rejected() -> None:
    with pytest.raises(ValueError, match="timezone aware"):
        build_decision_desk(source_kind=None, signal_session=None,
                            recorded_at_utc=None, candidates=[],
                            now=datetime(2026, 11, 15))


def patch_dependencies(monkeypatch: pytest.MonkeyPatch, *, live: bool = False) -> None:
    monkeypatch.setattr(research._MANAGER, "snapshot", lambda: SimpleNamespace(
        state="complete" if live else "idle",
        completed_at=datetime.now(UTC).isoformat() if live else None,
        latest_session=datetime.now(ZoneInfo("America/New_York")).date().isoformat() if live else None,
        candidates=[candidate("AAA", name="AAA Corporation Common Stock")],
    ))
    monkeypatch.setattr(research, "load_reference", lambda _path: None)
    monkeypatch.setattr(research, "load_industry_reference", lambda _path: None)
    monkeypatch.setattr(research, "build_prediction_report", lambda *args, **kwargs: {
        "status": "insufficient_evidence",
    })


def test_read_only_api_uses_saved_record_without_new_market_queries(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dependencies(monkeypatch)
    monkeypatch.setattr(research, "_latest_saved_checkpoint", lambda _path: {
        "signal_session": SESSION,
        "recorded_at_utc": datetime.now(UTC).isoformat(),
        "candidates": [candidate("AAA")],
    })
    monkeypatch.setattr(research, "AlpacaHistoryClient", lambda *args, **kw: (
        pytest.fail("Read-only decision endpoint must not fetch market bars")
    ))
    response = client().get("/api/research/decision-desk")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source_kind"] == "frozen_checkpoint"
    assert payload["candidates"][0]["symbol"] == "AAA"
    assert payload["prediction_status"] == "insufficient_evidence"


def test_corrupted_saved_research_is_not_partially_published(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dependencies(monkeypatch)
    def broken(_path: object) -> None:
        raise research.JournalError("/private/user/secret/checkpoint.json")
    monkeypatch.setattr(research, "_latest_saved_checkpoint", broken)
    response = client().get("/api/research/decision-desk")
    assert response.status_code == 503
    assert "secret" not in response.text
    assert "candidates" not in response.text


def test_prediction_audit_failure_does_not_invent_model_evidence(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dependencies(monkeypatch)
    monkeypatch.setattr(research, "_latest_saved_checkpoint", lambda _path: None)
    def bad_report(*_args: object, **_kwargs: object) -> None:
        raise research.PredictionEvidenceError("invalid")
    monkeypatch.setattr(research, "build_prediction_report", bad_report)
    response = client().get("/api/research/decision-desk")
    assert response.status_code == 200
    assert response.json()["prediction_status"] == "unavailable"


def test_missing_saved_checkpoint_shows_empty_state(monkeypatch: pytest.MonkeyPatch) -> None:
    patch_dependencies(monkeypatch)
    monkeypatch.setattr(research, "_latest_saved_checkpoint", lambda _path: None)
    response = client().get("/api/research/decision-desk")
    assert response.status_code == 200
    assert response.json()["candidates"] == []


def test_valid_imported_sec_filer_and_sic_evidence_is_displayed() -> None:
    from app.market_data.sec_identity import SecFiler, SecReference
    from app.market_data.sec_industry import SicEntry, SicReference

    ticker = SecReference(
        NOW - timedelta(days=1), "a" * 64,
        {"AAA": (SecFiler("0000001001", "Alpha Inc.", "Nasdaq"),)},
    )
    industry = SicReference(
        NOW - timedelta(days=1), "b" * 64, "a" * 64,
        {"0000001001": SicEntry("3571", "Electronic Computers")},
    )
    report = build_decision_desk(
        source_kind="frozen_checkpoint", signal_session=SESSION,
        recorded_at_utc=NOW.isoformat(), candidates=[candidate("AAA")],
        ticker_reference=ticker, industry_reference=industry, now=NOW,
    )
    item = report["candidates"][0]
    assert item["sec_filer"]["cik"] == "0000001001"
    assert item["sec_filer"]["status"] == "matched"
    assert item["sec_industry"]["code"] == "3571"
    assert item["sec_industry"]["status"] == "matched"


def test_sic_source_mismatch_does_not_mislabel_industry() -> None:
    from app.market_data.sec_identity import SecFiler, SecReference
    from app.market_data.sec_industry import SicEntry, SicReference

    ticker = SecReference(
        NOW - timedelta(days=1), "a" * 64,
        {"AAA": (SecFiler("0000001001", "Alpha Inc.", "Nasdaq"),)},
    )
    industry = SicReference(
        NOW - timedelta(days=1), "b" * 64, "wrong" + "a" * 59,
        {"0000001001": SicEntry("3571", "Electronic Computers")},
    )
    report = build_decision_desk(
        source_kind="frozen_checkpoint", signal_session=SESSION,
        recorded_at_utc=NOW.isoformat(), candidates=[candidate("AAA")],
        ticker_reference=ticker, industry_reference=industry, now=NOW,
    )
    assert report["candidates"][0]["sec_industry"]["status"] == "industry_reference_mismatched_reference"
    assert report["candidates"][0]["sec_industry"]["code"] is None


def test_recent_capture_cannot_relabel_old_signal_as_fresh() -> None:
    report = build_decision_desk(
        source_kind="frozen_checkpoint", signal_session="2026-10-01",
        recorded_at_utc=NOW.isoformat(), candidates=[candidate("AAA")], now=NOW,
    )
    assert report["source_recent"] is False
    assert report["candidates"][0]["quality_reason"] == "outdated_session"


def test_recent_completed_browser_scan_takes_precedence_over_saved_record(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_dependencies(monkeypatch, live=True)
    monkeypatch.setattr(research, "_latest_saved_checkpoint", lambda _path: (
        pytest.fail("Fresh website scan must be preferred over older saved record")
    ))
    response = client().get("/api/research/decision-desk")
    assert response.status_code == 200
    assert response.json()["source_kind"] == "website_scan"


def test_bad_sec_reference_prevents_partial_official_evidence(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    patch_dependencies(monkeypatch)
    monkeypatch.setattr(research, "_latest_saved_checkpoint", lambda _path: None)
    def corrupted(_root: object) -> None:
        raise research.SecIdentityError("/private/secret")
    monkeypatch.setattr(research, "load_reference", corrupted)
    response = client().get("/api/research/decision-desk")
    assert response.status_code == 503
    assert "private" not in response.text
    assert "candidates" not in response.text
