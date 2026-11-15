# Milestone 3E.1 — Browser research overview and budget scenarios

## Scope

The Dashboard now displays the saved research-journal status, any verified cumulative
statistics, and the latest **in-process** website scanner's top candidates.
`/planner` adds a budget allocation scenario. These are explicitly research/education
features, **not personalized financial advice, verified buy recommendations, or brokerage orders**.

### Scenario rules (predeclared, not model-optimized)

| Style | Broad-market ETF example (SPY) | Experimental individual stocks, opt-in only | Other/cash |
|---|---:|---:|---:|
| Cautious | 60% | 0% | 40% |
| Balanced | 65% | up to 20% | at least 15% |
| Growth-oriented | 70% | up to 20% | at least 10% |

Experimental ideas are drawn only from a **completed website scan or checksum-verified frozen
research-journal shortlist <= 96 hours old**, with a completed-data date no more than five
New York calendar days ago and explicit common-share-name evidence. The top two eligible names
receive at most 10% of the total budget each; no qualifying names means their slice stays cash.
Security names are **not verified instrument classifications**, and not forecasts. The scenario
never implies that the named ETF is priced or that shares can be bought at historical closes.
The user must actively opt into individual-stock ideas. The initial $100 example without opt-in
shows $65 as an illustrative broad-index ETF category and $35 as cash.

When no recent in-memory scan is available, the planner may use the latest independently pinned
forward research checkpoint, rechecking its original checksum before reading its shortlist.
The overview also displays the frozen shortlist after server restarts. Any tampered record fails closed.

The planner uses whole cents and maintains a hard ledger invariant:
`sum(allocation.amount_usd) == budget_usd`. Fractional-share quantities for individual
stocks are *indicative only*, derived from old adjusted closing prices. No executable ETF
quote is fetched. No order placement or automatic rebalancing is provided.

### Backend API

- `GET /api/research/overview`: existing pinned-and-verified cumulative forward research
  report plus latest frozen shortlist, without outcome-price downloads. Journal path from
  `STW_RESEARCH_DIR` or `~/StockTradingWebResearch`; if verification fails, returns HTTP 503
  with **no figures**.
- `POST /api/research/budget-plan`: budget amount + cautious/balanced/growth + optional
  stock-research opt-in. Reads a recent **completed website scan**, or if unavailable a
  recent checksum-verified **frozen checkpoint**; doesn't start a new scan or trade.

**Operational note:** the website's in-memory scanner state is lost on server restart.
Prospective journal records remain on disk; the planner can use a recent checksum-verified
journal shortlist instead. An old or corrupted journal does not supply stock ideas.

### Applying patch

Extract the patch into `StockTradingWeb` on a new `feature/research-dashboard-budget-planner`
branch from current `origin/main`, then run:

```bash
cd backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
cd ../frontend
pnpm exec vitest run
pnpm lint
pnpm build
```

Start the existing backend and frontend using the repository's README instructions.
The Research Overview is at `/`; the planner at `/planner`. Try `$100.00` before and
after a completed Find Opportunities scan, optionally enabling experimental ideas.

### Known limitations / later work

- Requires an actual current market price feed for executable share estimates.
- Needs verified common-share/ETF identities and user-defined goals, horizon, emergency
  reserves and real portfolio holdings before displaying personalized investment guidance.
- Today's descriptive momentum score is not a validated expected-return model.
- SPY is simply an illustrative example, not necessarily suitable or optimal for the user.
- Overlapping research holding periods are correlated, not a real portfolio equity curve.
- Existing market-wide scanner still includes instruments that its loose Alpaca eligibility
  classification cannot authoritatively verify; planner's additional screen is heuristic.
- The API inherits the application's existing authentication/deployment assumptions;
  don't expose private research data on a public unauthenticated server.
