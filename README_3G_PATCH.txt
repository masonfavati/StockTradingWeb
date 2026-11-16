StockTradingWeb — Milestone 3G: Research Decision Desk and Allocation Transparency
ONE consolidated feature patch. Apply onto already-merged main including Milestone 3F.

In ~/StockTradingWeb:
  git status -sb
  git fetch origin
  git switch main
  git pull --ff-only origin main
  git switch -c feature/research-decision-desk
  unzip -o ~/Downloads/StockTradingWeb_3G_Research_Decision_Desk.zip -d ~/StockTradingWeb

Backend (one suite):
  cd ~/StockTradingWeb/backend
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

Frontend (one suite):
  cd ~/StockTradingWeb/frontend
  pnpm exec vitest run
  pnpm lint
  pnpm build

Website: /decisions, /planner, /forecasts, dashboard shortlist link.
No database migration; no paid providers, broker calls, or trading actions added.

For full acceptance cases and limitations, read docs/MILESTONE_3G_RESEARCH_DECISION_DESK.md.
