"""SIC is SEC issuer metadata: absent or conflicting evidence must fail closed."""

import json
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from zipfile import ZipFile

import pytest

from app.market_data.sec_identity import install_reference
from app.market_data.sec_industry import (
    SecIndustryError,
    import_industry_archive,
    import_industry_files,
    load_industry_reference,
    review_sec_industry,
)

NOW = datetime(2026, 11, 15, 12, tzinfo=UTC)


def ticker_source(tmp_path: Path):  # type: ignore[no-untyped-def]
    source = tmp_path / "tickers.json"
    source.write_text(json.dumps({
        "fields": ["cik", "name", "ticker", "exchange"],
        "data": [[1001, "ALPHA", "AAA", "Nasdaq"], [1002, "BETA", "BBB", "NYSE"]],
    }))
    return install_reference(source, tmp_path, now=NOW)


def zipped(tmp_path: Path, first: str = "3571", second: str = "3571") -> Path:
    path = tmp_path / "submissions.zip"
    with ZipFile(path, "w") as archive:
        for cik, sic, description in ((1001, first, "Computer Hardware"),
                                      (1002, second, "Computer Hardware" if second == first else "Other")):
            archive.writestr(f"CIK{cik:010d}.json", json.dumps({
                "cik": cik, "sic": sic, "sicDescription": description,
            }))
        archive.writestr("notes/../not_a_cik.json", "should not be examined")
    return path


def test_import_and_load_only_compact_sic_metadata(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    ref = import_industry_archive(zipped(tmp_path), tmp_path, ticker, now=NOW)
    assert set(ref.entries) == {"0000001001", "0000001002"}
    assert ref.entries["0000001001"].sic == "3571"
    loaded = load_industry_reference(tmp_path)
    assert loaded == ref
    data = (tmp_path / "reference" / "sec_sic_reference_v1.json").read_text()
    assert "filings" not in data
    assert "ticker_source_sha256" in data


def test_same_sic_excludes_second_stock_without_inventing_sectors(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    sic = import_industry_archive(zipped(tmp_path), tmp_path, ticker, now=NOW)
    result = review_sec_industry(["AAA", "BBB"], ticker, sic, now=NOW)
    assert result["status"] == "checked"
    assert result["approved_symbols"] == ["AAA"]
    assert result["excluded"] == [{"symbol": "BBB", "reason": "same_reported_sic_as_prior_stock"}]
    assert [row["sic"] for row in result["matches"]] == ["3571", "3571"]


def test_different_sics_allow_both(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    sic = import_industry_archive(zipped(tmp_path, second="7372"), tmp_path, ticker, now=NOW)
    assert review_sec_industry(["AAA", "BBB"], ticker, sic, now=NOW)["approved_symbols"] == ["AAA", "BBB"]


def test_unknown_and_missing_sic_retain_cash(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    sic = import_industry_archive(zipped(tmp_path, second="0000"), tmp_path, ticker, now=NOW)
    result = review_sec_industry(["BBB"], ticker, sic, now=NOW)
    assert result["approved_symbols"] == []
    assert result["excluded"][0]["reason"] == "industry_sic_unavailable"
    assert review_sec_industry(["CCC"], ticker, sic, now=NOW)["approved_symbols"] == []


def test_missing_stale_and_mismatched_reference_fail_closed(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    sic = import_industry_archive(zipped(tmp_path), tmp_path, ticker, now=NOW)
    assert review_sec_industry(["AAA"], ticker, None, now=NOW)["status"] == "unavailable"
    assert review_sec_industry(["AAA"], ticker, sic, now=NOW + timedelta(days=31))["status"] == "stale"
    altered = replace(sic, ticker_source_sha256="0" * 64)
    assert review_sec_industry(["AAA"], ticker, altered, now=NOW)["status"] == "mismatched_reference"


def test_duplicate_archive_cik_refused(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    source = tmp_path / "submissions.zip"
    with ZipFile(source, "w") as archive:
        for name in ("CIK0000001001.json", "submissions/CIK0000001001.json"):
            archive.writestr(name, json.dumps({"cik": 1001, "sic": "3571", "sicDescription": "Computers"}))
    with pytest.raises(SecIndustryError, match="Duplicate"):
        import_industry_archive(source, tmp_path, ticker, now=NOW)


def test_modified_pinned_file_is_rejected(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    import_industry_archive(zipped(tmp_path), tmp_path, ticker, now=NOW)
    target = tmp_path / "reference" / "sec_sic_reference_v1.json"
    payload = json.loads(target.read_text())
    payload["entries"]["0000001001"]["description"] = "Unverified new industry"
    target.write_text(json.dumps(payload))
    with pytest.raises(SecIndustryError, match="modified"):
        load_industry_reference(tmp_path)


def test_no_implicit_overwrite(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    source = zipped(tmp_path)
    import_industry_archive(source, tmp_path, ticker, now=NOW)
    with pytest.raises(SecIndustryError, match="exists"):
        import_industry_archive(source, tmp_path, ticker, now=NOW)


def test_pinned_reference_rejects_symlink(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    import_industry_archive(zipped(tmp_path), tmp_path, ticker, now=NOW)
    target = tmp_path / "reference" / "sec_sic_reference_v1.json"
    target.unlink()
    target.symlink_to(tmp_path / "submissions.zip")
    with pytest.raises(SecIndustryError, match="regular file"):
        load_industry_reference(tmp_path)


def test_review_rejects_duplicate_symbols(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    sic = import_industry_archive(zipped(tmp_path), tmp_path, ticker, now=NOW)
    with pytest.raises(SecIndustryError, match="distinct"):
        review_sec_industry(["AAA", "AAA"], ticker, sic, now=NOW)


def test_import_two_small_sec_json_files(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    paths = []
    for cik, sic in ((1001, "3571"), (1002, "7372")):
        source = tmp_path / f"CIK{cik:010d}.json"
        source.write_text(json.dumps({"cik": cik, "sic": sic,
                                      "sicDescription": "SEC classification"}))
        paths.append(source)
    result = import_industry_files(paths, tmp_path, ticker, now=NOW)
    assert result.source_kind == "individual_json"
    assert len(result.entries) == 2
    assert load_industry_reference(tmp_path) == result
    reviewed = review_sec_industry(["AAA", "BBB"], ticker, result, now=NOW)
    assert reviewed["approved_symbols"] == ["AAA", "BBB"]
    assert reviewed["source_url"] == "https://data.sec.gov/submissions/"


def test_single_json_batch_rejects_unmatched_cik(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    source = tmp_path / "mismatch.json"
    source.write_text(json.dumps({"cik": 9999, "sic": "3571",
                                  "sicDescription": "Computers"}))
    with pytest.raises(SecIndustryError, match="not in the pinned"):
        import_industry_files([source], tmp_path, ticker, now=NOW)


def test_small_file_batch_is_all_or_nothing(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    valid = tmp_path / "valid.json"
    bad = tmp_path / "bad.json"
    valid.write_text(json.dumps({"cik": 1001, "sic": "3571", "sicDescription": "Computers"}))
    bad.write_text(json.dumps({"cik": 1002, "sic": "0000", "sicDescription": ""}))
    with pytest.raises(SecIndustryError, match="lacks valid SIC"):
        import_industry_files([valid, bad], tmp_path, ticker, now=NOW)
    assert load_industry_reference(tmp_path) is None


def test_small_file_batch_rejects_duplicate_cik(tmp_path: Path) -> None:
    ticker = ticker_source(tmp_path)
    sources = []
    for name in ("first.json", "second.json"):
        path = tmp_path / name
        path.write_text(json.dumps({"cik": 1001, "sic": "3571",
                                    "sicDescription": "Computers"}))
        sources.append(path)
    with pytest.raises(SecIndustryError, match="Repeated CIK"):
        import_industry_files(sources, tmp_path, ticker, now=NOW)
