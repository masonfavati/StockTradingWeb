"""Safely register the new universe model in the existing Alembic environment.

Run from StockTradingWeb repository root:
    python3 tools/register_universe_model.py
"""

from pathlib import Path


def register(content: str) -> str:
    old = "from app.models import historical_bar, instrument, watchlist"
    new = "from app.models import historical_bar, instrument, universe, watchlist"
    if new in content:
        return content
    if content.count(old) != 1:
        raise ValueError(
            "Could not find the expected Alembic model import. "
            "No changes made. Please inspect backend/alembic/env.py."
        )
    return content.replace(old, new, 1)


def main() -> None:
    target = Path("backend/alembic/env.py")
    if not target.is_file():
        raise SystemExit("Run this command from the StockTradingWeb repository root.")
    current = target.read_text(encoding="utf-8")
    try:
        updated = register(current)
    except ValueError as exc:
        raise SystemExit(str(exc)) from None
    if updated == current:
        print("The universe model is already registered in Alembic.")
    else:
        target.write_text(updated, encoding="utf-8")
        print("Registered universe model in backend/alembic/env.py.")


if __name__ == "__main__":
    main()
