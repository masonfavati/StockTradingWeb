StockTradingWeb — Milestone 3D.5 Cumulative Forward Performance
==============================================================
Apply to the current Git main branch AFTER 3D.4 has been merged.

Contents
  backend/app/analysis/forward_performance.py          NEW
  backend/app/analysis/forward_performance_cli.py      NEW
  backend/app/analysis/forward_outcomes.py             SMALL ROUNDING FIX (replaces 3D.4 file)
  backend/tests/test_forward_performance.py            NEW
  docs/MILESTONE_3D5_CUMULATIVE_PERFORMANCE.md         NEW

No database migration, no scheduler install, no source checkpoint mutation.

After unzipping into repository root:
  cd backend
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check
  uv run python -m app.analysis.forward_performance_cli --dir ~/StockTradingWebResearch

Optional machine JSON stdout:
  uv run python -m app.analysis.forward_performance_cli --dir ~/StockTradingWebResearch --json

The report is read-only (aside from possible calendar calls); it will not
request outcome PRICE bars or create portfolio return data while pending.
A single completed forward selection is NOT a validated profitable strategy.
