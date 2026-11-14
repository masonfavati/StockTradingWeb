"""An imperfect Alpaca directory must not invent data or lose valid assets."""

from uuid import UUID

import pytest

from app.market_data.universe_history import UniverseDataError, parse_asset_directory


def row(number: int, **overrides: object) -> dict[str, object]:
    item: dict[str, object] = {
        "id": str(UUID(int=number)),
        "class": "us_equity",
        "symbol": f"SYM{number}",
        "name": f"Company {number}",
        "exchange": "NASDAQ",
        "status": "active",
        "tradable": True,
    }
    item.update(overrides)
    return item


def test_missing_descriptive_metadata_is_preserved_as_missing() -> None:
    assets = parse_asset_directory([
        row(1, name=None, exchange=None, symbol=None),
        row(2, name="", exchange="", symbol=""),
        row(3, name=" Name "),
    ])
    assert len(assets) == 3
    assert (assets[0].symbol, assets[0].name, assets[0].exchange) == ("", "", "")
    assert (assets[1].symbol, assets[1].name, assets[1].exchange) == ("", "", "")
    assert assets[2].name == "Name"


def test_inactive_records_with_missing_names_are_not_discarded() -> None:
    assets = parse_asset_directory([
        row(5, status="inactive", tradable=False, name=None),
    ])
    assert assets[0].status == "inactive"
    assert assets[0].tradable is False
    assert assets[0].name == ""


@pytest.mark.parametrize(
    ("overrides", "field"),
    [
        ({"id": None}, "asset id"),
        ({"symbol": 123}, "symbol"),
        ({"name": 123}, "name type"),
        ({"exchange": 4}, "exchange"),
        ({"status": "unknown"}, "status"),
        ({"tradable": None}, "tradable flag"),
    ],
)
def test_essential_or_corrupt_fields_fail_with_actionable_detail(
    overrides: dict[str, object], field: str,
) -> None:
    with pytest.raises(UniverseDataError, match=field):
        parse_asset_directory([row(1), row(2, **overrides)])


def test_duplicate_asset_identity_still_refused() -> None:
    with pytest.raises(UniverseDataError, match="Duplicate"):
        parse_asset_directory([row(1), row(1, symbol="NEW")])
