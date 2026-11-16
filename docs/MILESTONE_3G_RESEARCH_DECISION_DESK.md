# Milestone 3G — Research Decision Desk and Allocation Transparency

**One complete patch.** No new paid service, trading integration, database table, migration, or automated purchase.

## Objective

Make the existing evidence usable without pretending historical ranking has validated future profitability. The Decision Desk explains a *recorded* market-wide shortlist and links to the existing cents-exact Investment Planner and prospective Forecast Lab.

## Changes

1. **Read-only `GET /api/research/decision-desk`.** Reuses the same source preference/freshness policy as `/budget-plan`: a recent completed website scan first, otherwise the latest checksum-verified frozen journal checkpoint. Never starts a new scan, queries quotes, requests historical bars, or places a trade.
2. **Bounded candidate research.** Shows at most 20 recorded candidates, their rank, historical adjusted close, 20/60-session return, annualized historical volatility, drawdown, approximate historical daily traded value, and scanner research score. Nonfinite/missing metrics are `null`, never JSON NaN. Uses the existing security-name and quality-screen criteria for per-candidate explanations. Apparent duplicate issuer/ticker names are flagged across the visible list. A quality pass is *not* a predicted return or final budget allocation.
3. **Locally imported SEC metadata.** Shows a per-candidate ticker→CIK filing-entity match and SEC SIC description only when the locally pinned references are valid, current, and internally consistent. Missing/stale/conflicting evidence is disclosed. These individual facts do *not* replace the planner's actual issuer/SIC concentration review.
4. **Prediction readiness.** Shows the prospective journal's overall validation status only. Does not publish guessed stock probabilities, reuse outcome information in scanner features, or authorize trading. If the prediction audit cannot be verified, status becomes `unavailable`.
5. **UI workflow.** New `/decisions` page in primary navigation, link from the Dashboard research shortlist, link to planner and Forecast Lab, candidate search and quality filter (client-side), evidence-refresh button (read-only).
6. **Allocation transparency.** New *Why is this amount still cash?* panel on `/planner` explains deliberate cash allocation, near-term horizon, affordable-loss cap, stale/missing shortlisted research, screening exclusions, and optional evidence-gate failures. The monetary computation and all previous safeguards are unchanged.
7. **Regression coverage.** New backend tests cover empty/stale/bad sources, quality decisions, SEC matches and mismatches, bad numbers, bounded output, source precedence, and no market-history requests. New frontend tests cover evidence displays, filter/search, unavailable journal and cash explanations.

## Data provenance and limitations

- The listed candidate names are vendor-supplied records; the market-wide scanner is heuristic. Past returns, prices, and volumes are not live quotes and do not establish tradeability, future profits, security-class verification, or tax suitability.
- The SEC's CIK and SIC classify a filing entity; they do not provide authoritative point-in-time common-share or revenue-segment identity. A single-candidate SIC match does not prove the total portfolio is diversified.
- The Decision Desk is descriptive. The planner *independently* enforces freshness, opt-ins, loss budget, two-stock cap, CIK/SIC concentration, historical co-movement, and gated prospective prediction evidence.
- A stale record may be displayed with a warning. Display **never** overrides planner freshness.
- An unverifiable frozen checkpoint or corrupted SEC file returns HTTP 503 without publishing partially verified identity details. Absent reference files are displayed as unavailable, not invented.
- No new automatic downloads or background tasks. The existing scheduled research command is unchanged.

## Manual acceptance

1. Run Backend quality suite: `uv run pytest -q`, `uv run ruff check .`, `uv run mypy app`, `uv run alembic check`.
2. Run Frontend quality suite: `pnpm exec vitest run`, `pnpm lint`, `pnpm build`.
3. Open the Dashboard; click **Explain the shortlist** or primary navigation **Research Decision Desk**.
4. With a registered shortlist, verify source kind, recorded session, capture timestamp and **up to 20** ranked candidates; verify one historical quality result and a meaningful reason for exclusions.
5. Filter to excluded candidates and search by ticker; no new backend call should occur after initial loading unless **Refresh saved evidence** is clicked.
6. If SEC metadata is missing, verify **Not verified** labels. With imported references, verify that filer name/CIK/SIC fields appear. Do not mistake this for a live exchange or revenue-segment classification.
7. If Forecast Lab is not yet validated, the Decision Desk must say **insufficient evidence** or **unavailable**, without inventing a stock-level probability.
8. Open `/planner`, enter $100/long-term/balanced and run without experimental stocks. The **Why is this amount still cash?** section should explain the default cash reserve. Then opt into experimental stocks and require prediction evidence; if the research gate is not passed, no model-dependent stock dollars should be invested.
9. Check the ordinary scanner, `/forecasts`, and planner gates for regressions. Verify no orders are placed.

## Files in the patch

- `backend/app/analysis/decision_desk.py` — pure, bounded presentation logic.
- `backend/app/api/research_dashboard.py` — one read-only endpoint.
- `backend/tests/test_decision_desk.py` — 17 backend tests.
- `frontend/src/features/research/DecisionDeskPage.tsx` — page.
- `frontend/src/features/research/DecisionDeskPage.test.tsx` — four UI tests.
- `frontend/src/features/research/allocationExplanation.ts` and `.test.ts` — explain retained cash, three tests.
- `frontend/src/features/research/researchApi.ts` — typed API response.
- `frontend/src/features/research/BudgetPlannerPage.tsx` — explanatory section and link.
- `frontend/src/features/research/ResearchOverview.tsx` — dashboard link.
- `frontend/src/App.tsx` — navigation and route.

The locally reconstructed project is incomplete and missing unrelated app modules; full Backend/Frontend suites are to be run on the canonical Mac repository before merging. Do not conflate local syntax checks and focused tests with a full CI pass.
