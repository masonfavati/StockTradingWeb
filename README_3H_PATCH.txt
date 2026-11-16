StockTradingWeb Milestone 3H — Budget Comparison Workspace

ONE feature patch. Adds an interactive, read-only /compare workflow for three
existing investment allocation styles, with exact cash accounting, source
consistency guards, local CSV export, and safe handoff to the full planner.

Apply at ~/StockTradingWeb on a new branch from the latest merged main:
  unzip -o ~/Downloads/StockTradingWeb_3H_Budget_Comparison_Workspace.zip -d ~/StockTradingWeb

No backend code, database migration, dependency change, API key, or extra
service. The page uses the already-existing /api/research/budget-plan API.

Quality and manual test instructions:
  docs/MILESTONE_3H_BUDGET_COMPARISON_WORKSPACE.md

Important: the scenario comparison is three independent HTTP requests. When
experimental stocks and historical evidence are enabled, up to three existing
bounded historical-data provider requests may be made. Inconsistent sources
cause the comparison to be withheld. No predictions or orders are invented.
