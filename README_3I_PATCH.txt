Milestone 3I — Independent Stock Price History Charts (single consolidated patch)

This patch is relative to merged 3H and adds:
  - On-demand, bounded Alpaca SIP historical daily closes (not dependent on Find Opportunities)
  - 1-month/3-month/1-year/5-year interactive history view and SPY comparison
  - historical scanner-date markers and navigation from scanner/Decision Desk/planner
  - strict data provenance, no future/incomplete candle, no fabricated price forecast
  - backend and frontend regression tests; documentation

Install:
  cd ~/StockTradingWeb
  git status -sb
  git fetch origin && git switch main && git pull --ff-only origin main
  git switch -c feature/independent-stock-history-charts
  unzip -o ~/Downloads/StockTradingWeb_3I_Independent_History_Charts.zip -d ~/StockTradingWeb

Backend suite:
  cd ~/StockTradingWeb/backend
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

Frontend suite:
  cd ~/StockTradingWeb/frontend
  pnpm exec vitest run
  pnpm lint
  pnpm build

Website: /history -> AAPL, range buttons, compare to SPY, session slider.
No new provider/service setup or migration. Needs the existing Alpaca credentials.

CAUTION: the existing 3F classifier predicts relative SPY outperformance, NOT
future dollar share prices. For scientific honesty this patch contains NO
speculative or fabricated forecast price curve. Graphical forecasts are reserved
for a separately trained and prospectively validated price-return model.
