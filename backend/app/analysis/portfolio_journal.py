"""Local, append-only, manual paper portfolio ledger. Never contacts a broker.

Stores exactly what the user recorded; absence of a record does not imply a
trade. Valuation is a separate optional completed-day price lookup.
"""

import fcntl
import json
import os
import re
import tempfile
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path
from threading import RLock
from typing import Any, Literal
from uuid import uuid4

_MAX_RECORDS = 2000
_MAX_BYTES = 1_000_000
_LOCK = RLock()
_SYMBOL_RE = re.compile(r"[A-Z][A-Z0-9.-]{0,19}\Z")


def validate_symbol(raw: str) -> str:
    if not isinstance(raw, str):
        raise PortfolioError("Invalid stock symbol.")
    symbol = raw.strip().upper()
    if _SYMBOL_RE.fullmatch(symbol) is None:
        raise PortfolioError("Invalid stock symbol.")
    return symbol


class PortfolioError(ValueError):
    """A trade or portfolio ledger cannot be trusted."""


def _decimal(raw: object, label: str, *, max_value: int, digits: int) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)):
        raise PortfolioError(f"{label} must be a decimal number.")
    try:
        value = Decimal(str(raw))
    except InvalidOperation as exc:
        raise PortfolioError(f"{label} must be a decimal number.") from exc
    exponent = value.as_tuple().exponent
    if (
        not value.is_finite() or value <= 0 or value > max_value
        or not isinstance(exponent, int) or exponent < -digits
    ):
        raise PortfolioError(f"{label} must be positive with at most {digits} decimal places.")
    return value


def _fee(raw: object) -> Decimal:
    if isinstance(raw, bool) or not isinstance(raw, (str, int, Decimal)):
        raise PortfolioError("Fee must be an amount in dollars.")
    try:
        amount = Decimal(str(raw))
    except InvalidOperation as exc:
        raise PortfolioError("Fee must be an amount in dollars.") from exc
    exponent = amount.as_tuple().exponent
    if (
        not amount.is_finite() or amount < 0 or amount > 100_000
        or not isinstance(exponent, int) or exponent < -2
    ):
        raise PortfolioError("Fee must be a nonnegative dollar amount with cents.")
    return amount


def _path(root: Path) -> Path:
    if root.is_symlink():
        raise PortfolioError("The research folder cannot be a symlink.")
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    target = root / "manual_portfolio_v1.json"
    if target.is_symlink():
        raise PortfolioError("Portfolio file cannot be a symlink.")
    return target



@contextmanager
def _file_lock(root: Path) -> Iterator[None]:
    """Hold an OS-wide exclusive lock for writes across API worker processes."""
    _path(root)
    lockfile = root / "manual_portfolio_v1.lock"
    if lockfile.is_symlink():
        raise PortfolioError("Portfolio lock cannot be a symlink.")
    descriptor = os.open(lockfile, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        yield
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def load_trades(root: Path) -> list[dict[str, Any]]:
    target = _path(root)
    if not target.exists():
        return []
    if not target.is_file() or target.stat().st_size > _MAX_BYTES:
        raise PortfolioError("Portfolio storage is not a valid local file.")
    try:
        data = json.loads(target.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError, UnicodeError) as exc:
        raise PortfolioError("Saved portfolio is damaged. No holdings were published.") from exc
    if not isinstance(data, dict) or data.get("version") != 1 or not isinstance(data.get("trades"), list):
        raise PortfolioError("Unexpected portfolio file structure.")
    rows = data["trades"]
    if len(rows) > _MAX_RECORDS:
        raise PortfolioError("Portfolio file exceeds supported limits.")
    # Build a typed, validated list instead of returning untyped JSON data.
    validated_rows: list[dict[str, Any]] = []
    for row in rows:
        if not isinstance(row, dict):
            raise PortfolioError("Portfolio file exceeds supported limits.")
        validated_rows.append(row)
    # Reconstruct and validate all records before returning the data.
    summary_trades(validated_rows)
    return validated_rows


def _write(root: Path, rows: list[dict[str, Any]]) -> None:
    target = _path(root)
    payload = json.dumps({"version": 1, "trades": rows}, separators=(",", ":"), allow_nan=False)
    if len(payload.encode()) > _MAX_BYTES:
        raise PortfolioError("Portfolio storage limit reached.")
    name: str | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="w", encoding="utf-8", prefix=".portfolio-", suffix=".json",
            dir=root, delete=False,
        ) as handle:
            name = handle.name
            os.fchmod(handle.fileno(), 0o600)
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(name, target)
    finally:
        if name is not None and os.path.exists(name):
            os.unlink(name)


def summary_trades(
    rows: list[dict[str, Any]], quotes: dict[str, tuple[Decimal, str]] | None = None,
) -> dict[str, Any]:
    lots: dict[str, list[dict[str, Decimal]]] = {}
    realized = Decimal(0)
    for row in sorted(rows, key=lambda item: str(item.get("date", ""))):
        if not all(key in row for key in ("symbol", "action", "date", "id")):
            raise PortfolioError("Incomplete transaction record.")
        symbol = validate_symbol(row["symbol"])
        try:
            session = date.fromisoformat(row["date"])
        except (TypeError, ValueError) as exc:
            raise PortfolioError("Invalid recorded trade date.") from exc
        if session > date.today() or session < date(1990, 1, 1):
            raise PortfolioError("Recorded trade date outside supported range.")
        action = row["action"]
        existing = lots.setdefault(symbol, [])
        if action == "split":
            ratio = _decimal(row.get("ratio"), "Split ratio", max_value=1000, digits=6)
            if not existing:
                raise PortfolioError("Cannot adjust shares without an existing holding.")
            for lot in existing:
                lot["shares"] *= ratio
            continue
        if action not in ("buy", "sell"):
            raise PortfolioError("Unknown transaction type.")
        shares = _decimal(row.get("shares"), "Shares", max_value=1_000_000, digits=6)
        price = _decimal(row.get("price_usd"), "Share price", max_value=10_000_000, digits=4)
        fees = _fee(row.get("fee_usd", "0"))
        if action == "buy":
            existing.append({"shares": shares, "cost": shares * price + fees})
            continue
        if shares > sum((lot["shares"] for lot in existing), Decimal(0)):
            raise PortfolioError(f"Cannot sell more {symbol} shares than were recorded as owned.")
        remaining = shares
        cost = Decimal(0)
        while remaining > 0:
            lot = existing[0]
            consumed = min(remaining, lot["shares"])
            fraction = consumed / lot["shares"]
            allocated_cost = lot["cost"] * fraction
            cost += allocated_cost
            lot["cost"] -= allocated_cost
            lot["shares"] -= consumed
            remaining -= consumed
            if lot["shares"] == 0:
                existing.pop(0)
        realized += shares * price - fees - cost
    holdings = []
    total_value = Decimal(0)
    for symbol, symbol_lots in sorted(lots.items()):
        shares = sum((lot["shares"] for lot in symbol_lots), Decimal(0))
        if shares <= 0:
            continue
        invested = sum((lot["cost"] for lot in symbol_lots), Decimal(0))
        quote = quotes.get(symbol) if quotes else None
        value = shares * quote[0] if quote else None
        if value is not None:
            total_value += value
        holdings.append({
            "symbol": symbol, "shares": str(shares.normalize()),
            "cost_basis_usd": f"{invested:.2f}",
            "last_completed_close_usd": str(quote[0]) if quote else None,
            "last_price_date": quote[1] if quote else None,
            "estimated_value_usd": f"{value:.2f}" if value is not None else None,
            "unrealized_gain_usd": f"{value - invested:.2f}" if value is not None else None,
            "unrealized_gain_pct": round(float((value / invested - 1) * 100), 2)
            if value is not None and invested else None,
        })
    all_valued = all(row["estimated_value_usd"] is not None for row in holdings)
    return {
        "holdings": holdings,
        "recorded_trades": len(rows),
        "realized_gain_usd": f"{realized:.2f}",
        "estimated_portfolio_value_usd": f"{total_value:.2f}" if all_valued else None,
        "valuation_complete": all_valued,
        "as_of": datetime.now().astimezone().isoformat(),
        "caveat": (
            "Transactions are manual records, not brokerage confirmations. Market values "
            "use last completed daily closes, not executable quotes. Splits must be "
            "recorded using the share-adjustment action or holdings may be wrong; "
            "dividends and taxes are not included. No trades are placed."
        ),
    }


def add_trade(
    root: Path, *, action: Literal["buy", "sell", "split"], symbol: str,
    day: date, shares: Decimal | None = None, price_usd: Decimal | None = None,
    fee_usd: Decimal = Decimal(0), ratio: Decimal | None = None,
) -> dict[str, Any]:
    if day > date.today() or day < date(1990, 1, 1):
        raise PortfolioError("Enter an actual past or current trade date.")
    ticker = validate_symbol(symbol)
    item: dict[str, Any] = {
        "id": uuid4().hex, "action": action, "symbol": ticker, "date": day.isoformat(),
    }
    if action == "split":
        if ratio is None:
            raise PortfolioError("Enter the share adjustment ratio.")
        item["ratio"] = str(_decimal(ratio, "Split ratio", max_value=1000, digits=6))
    elif action in ("buy", "sell"):
        if shares is None or price_usd is None:
            raise PortfolioError("Enter the actual share quantity and price.")
        item.update({
            "shares": str(_decimal(shares, "Shares", max_value=1_000_000, digits=6)),
            "price_usd": str(_decimal(price_usd, "Share price", max_value=10_000_000, digits=4)),
            "fee_usd": str(_fee(fee_usd)),
        })
    else:
        raise PortfolioError("Unknown transaction action.")
    with _LOCK, _file_lock(root):
        rows = load_trades(root)
        if len(rows) >= _MAX_RECORDS:
            raise PortfolioError("Maximum manual transaction count reached.")
        rows.append(item)
        summary_trades(rows)
        _write(root, rows)
    return item


def undo_last_trade(root: Path, trade_id: str) -> None:
    """Explicit ID check protects against accidentally deleting another entry."""
    with _LOCK, _file_lock(root):
        rows = load_trades(root)
        if not rows or rows[-1].get("id") != trade_id:
            raise PortfolioError("Only the most recent transaction can be undone.")
        _write(root, rows[:-1])
