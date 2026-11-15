"""SEC filer cross-reference is evidence, not proof of common shares or sector."""

import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from pathlib import Path

import pytest

from app.analysis.budget_planner import make_budget_plan
from app.market_data.sec_identity import (
    SecIdentityError,
    install_reference,
    load_reference,
    review_sec_identity,
)

NOW = datetime(2026, 11, 15, 7, tzinfo=UTC)


def source_json(tmp_path: Path, rows: list[list[object]]) -> Path:
    source = tmp_path / "company_tickers_exchange.json"
    source.write_text(json.dumps({
        "fields": ["cik", "name", "ticker", "exchange"], "data": rows,
    }), encoding="utf-8")
    return source


def rows() -> list[list[object]]:
    return [
        [1001, "ALPHA INC", "AAA", "Nasdaq"],
        [1002, "BETA CORP", "BBB", "NYSE"],
        [1001, "ALPHA INC", "AAC", "Nasdaq"],
        [2000, "INDEX FUND", "ETF", "NYSE Arca"],
        [3000, "OTC CO", "OTCC", "OTC"],
    ]


def candidates() -> list[dict[str, object]]:
    return [
        {"symbol": symbol, "name": f"{symbol} Common Stock", "last_session": "2026-11-13",
         "adjusted_close": 21.0, "annualized_volatility_pct": 25.0,
         "drawdown_60d_pct": -5.0, "approx_daily_dollar_volume": 12_000_000.0}
        for symbol in ("AAA", "BBB")
    ]


def test_import_and_offline_reload(tmp_path: Path) -> None:
    imported = install_reference(source_json(tmp_path, rows()), tmp_path / "research", now=NOW)
    loaded = load_reference(tmp_path / "research")
    assert loaded == imported
    assert loaded is not None
    assert loaded.entries["AAA"][0].cik == "0000001001"
    assert loaded.entries["AAA"][0].exchange == "Nasdaq"
    assert len(loaded.source_sha256) == 64
    assert (tmp_path / "research/reference/sec_ticker_reference_v1.json").exists()


def test_read_reference_optional_when_not_installed(tmp_path: Path) -> None:
    assert load_reference(tmp_path) is None


def test_import_refuses_overwrite_without_explicit_replace(tmp_path: Path) -> None:
    src = source_json(tmp_path, rows())
    install_reference(src, tmp_path, now=NOW)
    with pytest.raises(SecIdentityError, match="already exists"):
        install_reference(src, tmp_path, now=NOW)
    assert install_reference(src, tmp_path, replace=True, now=NOW).entries["AAA"]


def test_import_rejects_wrong_format(tmp_path: Path) -> None:
    source = source_json(tmp_path, rows())
    source.write_text(json.dumps({"data": rows(), "fields": ["ticker", "cik"]}))
    with pytest.raises(SecIdentityError, match="SEC company"):
        install_reference(source, tmp_path)


def test_import_rejects_duplicate_json_fields(tmp_path: Path) -> None:
    source = source_json(tmp_path, rows())
    source.write_text('{"fields": [], "fields": [], "data": []}')
    with pytest.raises(SecIdentityError, match="Duplicate"):
        install_reference(source, tmp_path)


def test_import_rejects_invalid_cik(tmp_path: Path) -> None:
    with pytest.raises(SecIdentityError, match="Invalid SEC"):
        install_reference(source_json(tmp_path, [[True, "A", "AAA", "Nasdaq"]]), tmp_path)


def test_import_rejects_symlink(tmp_path: Path) -> None:
    source = source_json(tmp_path, rows())
    link = tmp_path / "redirected.json"
    link.symlink_to(source)
    with pytest.raises(SecIdentityError, match="ordinary"):
        install_reference(link, tmp_path / "research")


def test_detects_pinned_reference_edit(tmp_path: Path) -> None:
    install_reference(source_json(tmp_path, rows()), tmp_path, now=NOW)
    target = tmp_path / "reference/sec_ticker_reference_v1.json"
    body = json.loads(target.read_text())
    body["data"][0][1] = "EDITED"
    target.write_text(json.dumps(body))
    with pytest.raises(SecIdentityError, match="modified"):
        load_reference(tmp_path)


def test_review_approves_two_distinct_filers(tmp_path: Path) -> None:
    ref = install_reference(source_json(tmp_path, rows()), tmp_path, now=NOW)
    review = review_sec_identity(["AAA", "BBB"], ref, now=NOW)
    assert review["status"] == "checked"
    assert review["approved_symbols"] == ["AAA", "BBB"]
    assert review["matches"][0]["cik"] == "0000001001"
    assert "not proof" in review["caveat"]


def test_review_rejects_repeat_cik_not_just_repeat_name(tmp_path: Path) -> None:
    ref = install_reference(source_json(tmp_path, rows()), tmp_path, now=NOW)
    review = review_sec_identity(["AAA", "AAC"], ref, now=NOW)
    assert review["approved_symbols"] == ["AAA"]
    assert review["excluded"] == [
        {"symbol": "AAC", "reason": "same_sec_filer_as_prior_stock"},
    ]


def test_review_rejects_ambiguous_ticker(tmp_path: Path) -> None:
    ref = install_reference(source_json(tmp_path, rows() + [[999, "DIFFERENT", "AAA", "NYSE"]]),
                            tmp_path, now=NOW)
    review = review_sec_identity(["AAA"], ref, now=NOW)
    assert review["approved_symbols"] == []
    assert review["excluded"][0]["reason"] == "sec_ticker_ambiguous"


def test_review_rejects_missing_and_otc(tmp_path: Path) -> None:
    ref = install_reference(source_json(tmp_path, rows()), tmp_path, now=NOW)
    assert review_sec_identity(["MISSING", "OTCC"], ref, now=NOW)["approved_symbols"] == []


def test_review_rejects_stale_reference(tmp_path: Path) -> None:
    ref = install_reference(source_json(tmp_path, rows()), tmp_path, now=NOW - timedelta(days=40))
    review = review_sec_identity(["AAA"], ref, now=NOW)
    assert review["status"] == "stale"
    assert not review["approved_symbols"]


def test_missing_reference_fails_closed() -> None:
    review = review_sec_identity(["AAA", "BBB"], None, now=NOW)
    assert review["status"] == "unavailable"
    assert len(review["excluded"]) == 2


def test_no_ticker_punctuation_guess(tmp_path: Path) -> None:
    ref = install_reference(source_json(tmp_path, [[1001, "BERK", "BRK-B", "NYSE"]]),
                            tmp_path, now=NOW)
    assert review_sec_identity(["BRK.B"], ref, now=NOW)["approved_symbols"] == []


def test_sec_gate_retains_rejected_dollars_as_cash(tmp_path: Path) -> None:
    same_filer = [[1001, "ALPHA INC", "AAA", "Nasdaq"],
                  [1001, "ALPHA CLASS B", "BBB", "NYSE"]]
    ref = install_reference(source_json(tmp_path, same_filer), tmp_path, now=NOW)
    # Different names can still share a single official SEC CIK.
    review = review_sec_identity(["AAA", "BBB"], ref, now=NOW)
    assert review["excluded"][0]["reason"] == "same_sec_filer_as_prior_stock"
    sample = candidates()
    result = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        scan_state="complete", scan_completed_at=NOW.isoformat(),
        scan_latest_session="2026-11-13", candidates=sample, now=NOW,
        require_sec_identity=True, sec_identity_review=review,
    )
    assert [(r["symbol"], r["amount_usd"]) for r in result["allocation"]] == [
        ("SPY", "65.00"), ("AAA", "10.00"), (None, "25.00"),
    ]
    assert result["quality_review"]["sec_gated_count"] == 1


def test_sec_gate_missing_reference_keeps_all_stock_slices_cash() -> None:
    result = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        scan_state="complete", scan_completed_at=NOW.isoformat(),
        scan_latest_session="2026-11-13", candidates=candidates(), now=NOW,
        require_sec_identity=True, sec_identity_review=None,
    )
    assert [(r["symbol"], r["amount_usd"]) for r in result["allocation"]] == [
        ("SPY", "65.00"), (None, "35.00"),
    ]


def test_default_plan_unchanged_when_sec_opt_in_off() -> None:
    result = make_budget_plan(
        Decimal(100), "balanced", allow_experimental_stocks=True,
        scan_state="complete", scan_completed_at=NOW.isoformat(),
        scan_latest_session="2026-11-13", candidates=candidates(), now=NOW,
    )
    assert [r["amount_usd"] for r in result["allocation"]] == [
        "65.00", "10.00", "10.00", "15.00",
    ]
    assert result["sec_identity_review"] is None
