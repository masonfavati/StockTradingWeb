StockTradingWeb — Milestone 3E.2 Horizon and Affordable-Loss Planner

Apply to feature/horizon-risk-budget-planner from latest merged origin/main.
The ZIP overwrites only 5 existing planner files, adds 2 backend tests, and
adds 1 documentation file. No database migration or scheduler modification.

Check Backend: uv run pytest -q; uv run ruff check .; uv run mypy app; uv run alembic check
Check Frontend: pnpm exec vitest run; pnpm lint; pnpm build

See docs/MILESTONE_3E2_HORIZON_AND_LOSS_PLANNER.md for calculations,
assumptions and limitations. This is illustrative research planning only.
