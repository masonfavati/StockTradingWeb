StockTradingWeb — COMPLETE Milestone 3F (single consolidated patch)
============================================================

This is ONE complete feature patch, not a sequence of mini-milestones.
Apply ONLY after Milestone 3E.6 is merged into main.

1) cd ~/StockTradingWeb
   git status -sb
   git fetch origin
   git switch main
   git pull --ff-only origin main
   git switch -c feature/prospective-prediction-validation

2) unzip -o ~/Downloads/StockTradingWeb_3F_Complete_Prediction_Validation.zip -d ~/StockTradingWeb

3) BACKEND suite:
   cd ~/StockTradingWeb/backend
   uv run pytest -q
   uv run ruff check .
   uv run mypy app
   uv run alembic check

4) FRONTEND suite:
   cd ~/StockTradingWeb/frontend
   pnpm exec vitest run
   pnpm lint
   pnpm build

5) Open /forecasts and /planner. Enable the experimental-stock switch
   and optionally 'Require prospective prediction evidence'. With very
   few real matured journal outcomes, 'insufficient_evidence' and cash
   retention are CORRECT behavior, not evidence of a broken patch.

6) Read docs/MILESTONE_3F_COMPLETE_PROSPECTIVE_PREDICTION.md for the
   detailed protocol, numerical predeclared gates, limitations, and CLI.

This patch adds no database migration, no new paid service, no trading,
and no ML-library dependency. The already-installed morning scheduler
now also evaluates up to five genuinely matured registered outcomes after
its existing capture attempt; it can make bounded historical Alpaca
requests in that window. No added LaunchAgent installation required.

The locally reconstructed project is missing some unrelated original
modules. Complete Backend and Frontend verification must run on Mac.
