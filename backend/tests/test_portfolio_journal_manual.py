"""Manual trades: FIFO, sell limits, split adjustment, damaged-file rejection."""

import json
from datetime import date
from decimal import Decimal
from pathlib import Path

import pytest

from app.analysis.portfolio_journal import (
    PortfolioError,
    add_trade,
    load_trades,
    summary_trades,
    undo_last_trade,
)


def buy(root: Path, *, shares: str, price: str, fee: str = "0") -> dict:
    return add_trade(root, action="buy", symbol="AAPL", day=date(2026, 1, 12),
                     shares=Decimal(shares), price_usd=Decimal(price), fee_usd=Decimal(fee))


def test_fifo_partial_sale_and_cash_fees(tmp_path: Path) -> None:
    buy(tmp_path, shares="2", price="10", fee="2")
    buy(tmp_path, shares="3", price="20")
    add_trade(tmp_path, action="sell", symbol="AAPL", day=date(2026, 2, 12),
              shares=Decimal(3), price_usd=Decimal(30), fee_usd=Decimal(1))
    total = summary_trades(load_trades(tmp_path))
    assert total["holdings"][0]["shares"] == "2"
    assert total["holdings"][0]["cost_basis_usd"] == "40.00"
    assert total["realized_gain_usd"] == "47.00"


def test_split_preserves_basis_and_changes_share_count(tmp_path: Path) -> None:
    buy(tmp_path, shares="2", price="50")
    add_trade(tmp_path, action="split", symbol="AAPL", day=date(2026, 3, 12), ratio=Decimal(4))
    total = summary_trades(load_trades(tmp_path))
    assert total["holdings"][0]["shares"] == "8"
    assert total["holdings"][0]["cost_basis_usd"] == "100.00"


def test_oversell_rejected_without_writing(tmp_path: Path) -> None:
    buy(tmp_path, shares="1", price="20")
    with pytest.raises(PortfolioError, match="more"):
        add_trade(tmp_path, action="sell", symbol="AAPL", day=date(2026, 1, 20),
                  shares=Decimal(2), price_usd=Decimal(20))
    assert len(load_trades(tmp_path)) == 1


def test_undo_only_latest_entry(tmp_path: Path) -> None:
    first = buy(tmp_path, shares="1", price="10")
    second = buy(tmp_path, shares="1", price="11")
    with pytest.raises(PortfolioError, match="most recent"):
        undo_last_trade(tmp_path, first["id"])
    undo_last_trade(tmp_path, second["id"])
    assert len(load_trades(tmp_path)) == 1


def test_corrupt_file_is_not_silently_reset(tmp_path: Path) -> None:
    target = tmp_path / "manual_portfolio_v1.json"
    target.write_text('{"version":1,"trades":[{"action":"sell"}]}')
    with pytest.raises(PortfolioError):
        load_trades(tmp_path)
    assert json.loads(target.read_text())["trades"]


def test_symlink_store_rejected(tmp_path: Path) -> None:
    dest = tmp_path / "private.json"
    dest.write_text('private')
    (tmp_path / "manual_portfolio_v1.json").symlink_to(dest)
    with pytest.raises(PortfolioError, match="symlink"):
        load_trades(tmp_path)
