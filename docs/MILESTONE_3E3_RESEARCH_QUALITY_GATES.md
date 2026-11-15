# Milestone 3E.3 — Historical research-quality gates for optional stock ideas

This extends the **illustrative** Investment Budget Planner from 3E.2. It does **not** change the market scanner's recorded predictions, score, data downloads, installed LaunchAgent, database, or the fixed SPY/cash horizon examples. It places a conservative extra screen between the scanner's *top-20 already-ranked candidates* and the *optional* individual-stock dollar slices.

## Gating rules (educational heuristics, not empirically tuned)

Every optional stock candidate must:

- Match a recent, completed scan or checksum-verified frozen research shortlist and the scan's latest completed market session.
- Have **positive ordinary/common-share name evidence** under the existing heuristic classifier, with no conflicting warrant/ETF/unit/preferred/ADR indicators. This is **not a verified security type**.
- Have a valid historical split-adjusted close **at least $5**. This is *not* a valuation test.
- Have approximate mean daily adjusted-close × volume over recent scanner sessions **at least $5,000,000**. This is *not* current executable liquidity, slippage, or spread data.
- Have historical annualized close-to-close volatility **greater than 0 and at most 80%**.
- Have a 60-session close-to-peak drawdown between **−25% and 0%**, inclusive.
- Have all required metrics present and finite (never replace missing metrics with guesses).

Preserve the scanner's original rank order, while taking at most **two** optional individual-stock ideas, **10% of the budget per name**, with one candidate per *approximate normalized issuer name*. This is only an anti-duplicate-share-class heuristic, **not** verified entity/sector attribution or a cross-asset correlation model. The existing SPY/core-first allocation and nominal-at-risk budget cap are unchanged. Rejected or unavailable experimental slices remain **cash**.

The API response adds a `quality_review` with the screen version, `applied` flag, ranked shortlist count checked, selected count, per-reason exclusions, explicit thresholds, and caveat. The `/planner` page displays this report when the experimental opt-in is enabled; no new input is required. This does not prove any stock is safe or that its expected return is positive.

## Important limitations

- The report examines the **at-most-20 saved/returned shortlist candidates**, not the full market directory. The original scanner may have already excluded other securities.
- Previous and new rules are not validated return forecasts. Price thresholds, liquidity proxies, volatility/drawdowns, issuer names and score ranking are research heuristics. No industry/sector diversification, factor correlation, live execution, dividend handling, or verified security identity is modeled.
- Adjusted historical closing prices are **not executable order quotes**; actual fraction eligibility, costs, taxes and broker fills are unverified. No orders are placed.
- Research records are unchanged and do not have their methodology retroactively altered; the budget planner's new screener only affects new on-screen examples.

## Apply and verify

Use a new branch from `origin/main` and unzip the patch at the repository root, outside the Mac's 8–9 a.m. New York forward-scan window. Before staging, inspect for secrets and local research data.

**Backend**

```bash
cd ~/StockTradingWeb/backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

**Frontend**

```bash
cd ~/StockTradingWeb/frontend
pnpm exec vitest run
pnpm lint
pnpm build
```

Start the app and try `/planner`: Balanced, `$100`, 5+ years, experimental ideas enabled. If two screened candidates qualify, expect $65 SPY, $10 per satellite, and $15 cash. If none qualify, expect $65 SPY and $35 cash. Try a `$20` affordable-loss cap and a short horizon to verify cash/risk rules still dominate. Read the screen report and exclusion reasons on the page.
