StockTradingWeb — Milestone 3E.3: Research quality screens and capped experimental stock ideas

Apply on new feature branch from the latest merged main; unpack at repository root.
Changes: additional historical candidate quality gates; user-visible screen/exclusion explanations; expanded regression tests; documentation.

No database migration, API key changes, new dependencies, background scheduling changes, trading actions, or new paid services.

Backend checks: uv run pytest -q ; uv run ruff check . ; uv run mypy app ; uv run alembic check
Frontend checks: pnpm exec vitest run ; pnpm lint ; pnpm build

The reconstructed offline environment verified focused Python tests and TypeScript/JSX syntax only. Run both full quality suites against your actual Mac repository and check /planner before merging.
