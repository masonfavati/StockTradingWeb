StockTradingWeb - Milestone 3E.4 (first phase): Portfolio Co-Movement

This additive patch extends the working 3E.3 budget planner.
It does NOT add verified security IDs, verified sectors, or optimized portfolio forecasts.

Run from repo root after updating main and creating a feature branch:

  unzip -o ~/Downloads/StockTradingWeb_3E4_Portfolio_Comovement.zip -d ~/StockTradingWeb

Backend suite (from backend):
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

Frontend suite (from frontend):
  pnpm exec vitest run
  pnpm lint
  pnpm build

View /planner. Enable experimental stocks and the checked-by-default historical
co-movement review to run a bounded, source-date-limited price comparison.
A missing or failed provider response keeps experimental dollars in cash.

No migrations. No scheduling changes. No orders. No files in research journal edited.
Full repository checks must run on your Mac; reconstructed local repo is partial.
