StockTradingWeb Milestone 3D.1 — frozen prospective outcome evaluation

This patch ADDS ONLY the following files:
- backend/app/analysis/forward_evaluation.py
- backend/app/analysis/evaluate_forward_cli.py
- backend/tests/test_forward_evaluation.py
- docs/MILESTONE_3D1_FORWARD_OUTCOME.md

It does not modify existing source files, migrations, API credentials, the
recorded prospective checkpoint, or the user's database.

Create branch from the merged main:
  cd ~/StockTradingWeb
  git fetch origin
  git switch -c feature/forward-outcome-evaluation origin/main

Unzip after downloading:
  unzip -l ~/Downloads/StockTradingWeb_3D1_Forward_Outcome.zip
  unzip -o ~/Downloads/StockTradingWeb_3D1_Forward_Outcome.zip -d ~/StockTradingWeb

Then check:
  cd ~/StockTradingWeb/backend
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

See docs/MILESTONE_3D1_FORWARD_OUTCOME.md for the status-only audit command,
and the later outcome evaluation command. The saved 3C.2 JSON stays outside
Git and is never changed by the evaluator.
