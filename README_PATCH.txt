StockTradingWeb 3D.4 — Bounded Prospective Outcome Journal

Additive patch, no migration and no changes to the installed LaunchAgent.
Files:
  backend/app/analysis/forward_outcomes.py
  backend/app/analysis/forward_outcomes_cli.py
  backend/tests/test_forward_outcomes.py
  docs/MILESTONE_3D4_OUTCOMES.md

Create a fresh branch from merged main, unzip into repository, then check:
  cd backend
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

Read-only integration test (may query Alpaca exchange calendar, NOT price bars):
  uv run python -m app.analysis.forward_outcomes_cli status --dir ~/StockTradingWebResearch

Only after a registered checkpoint matures and after inspecting its frozen
identity, explicitly process at most one:
  uv run python -m app.analysis.forward_outcomes_cli evaluate-ready \
    --dir ~/StockTradingWebResearch --limit 1

No automatic scheduling is installed by this patch; no stock orders are placed.
