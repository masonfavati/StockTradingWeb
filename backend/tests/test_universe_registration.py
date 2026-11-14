"""Ensure Alembic registration is a safe, idempotent targeted change."""

import runpy
from pathlib import Path

import pytest

REGISTER = runpy.run_path(
    str(Path(__file__).resolve().parents[2] / "tools" / "register_universe_model.py")
)["register"]


def test_migration_registration_preserves_comments_and_is_idempotent() -> None:
    source = "from app.models import historical_bar, instrument, watchlist  # noqa: F401\n"
    modified = REGISTER(source)
    assert modified == (
        "from app.models import historical_bar, instrument, universe, watchlist  # noqa: F401\n"
    )
    assert REGISTER(modified) == modified


def test_migration_registration_does_not_guess_at_unfamiliar_code() -> None:
    with pytest.raises(ValueError):
        REGISTER("from app.models import something_else\n")
