StockTradingWeb Milestone 3E.1 — Research Dashboard + Illustrative Investment Budget Planner

PATCH CONTENTS
- backend/app/main.py (adds /api/research router)
- backend/app/analysis/budget_planner.py (exact-cent risk-styled scenario engine)
- backend/app/api/research_dashboard.py (verified verified journal/latest checkpoint overview + planner API)
- backend/tests/test_budget_planner.py
- frontend/src/App.tsx (Dashboard overview + /planner)
- frontend/src/features/research/researchApi.ts
- frontend/src/features/research/ResearchOverview.tsx
- frontend/src/features/research/BudgetPlannerPage.tsx
- frontend/src/features/research/BudgetPlannerPage.test.tsx
- frontend/src/features/research/ResearchOverview.test.tsx
- docs/MILESTONE_3E1_RESEARCH_DASHBOARD_AND_PLANNER.md

NO automatic trades, new external service, database migration or LaunchAgent changes.
The planner is NOT a validated investment recommendation. See docs for research safeguards.
Run backend and frontend quality suites before opening PR.
