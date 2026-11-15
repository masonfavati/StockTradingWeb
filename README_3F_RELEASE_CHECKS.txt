ONE consolidated 3F patch. For review/verification after applying onto 3E.6 main:

BACKEND: uv run pytest -q ; uv run ruff check . ; uv run mypy app ; uv run alembic check
FRONTEND: pnpm exec vitest run ; pnpm lint ; pnpm build

Live test: /forecasts loads; /planner "Require prospective prediction evidence" option
properly leaves experimental dollars as cash when the journal has not yet
accumulated enough completed, genuinely prospective outcomes.

The existing Mac 08:00-08:59 ET scheduled-capture command now attempts to
process up to FIVE mature outcome audits after capture; additional historical
Alpaca requests may occur. No trading or paid services.
