StockTradingWeb 3I - Quality-gate corrections

Apply to the existing feature/independent-stock-history-charts branch AFTER the full 3I patch.
This is not a new feature milestone. Replaces two files only.

Changes:
- Backend: enumerate page bounds; narrow optional benchmark date for mypy.
- Frontend: derive ticker draft from query instead of synchronous effect; associate history result with the active ticker/period/benchmark request, and use asynchronous request callbacks to publish data, eliminating both React effect warnings.

After applying, run backend pytest/ruff/mypy and frontend vitest/lint/build.
