# Milestone 3E.2 — Horizon & affordable-loss budget planning

This is an **illustrative allocation calculator**, NOT a personalized investment
recommendation, return forecast, broker order, or mathematically optimal portfolio.
It extends the `/planner` page introduced in Milestone 3E.1.

## What changed

- Input a **time horizon**: within 1 year; 1–5 years; 5+ years.
- Optionally input the **maximum dollar amount you could afford to lose**.
  No leverage or margin is assumed. The planner does not assign more than that
  dollar amount to risky assets, in the deliberately extreme hypothetical case
  that the entire invested principal is lost. **This does not guarantee losses
  are capped, predict drawdowns, or account for all cash risks.**
- Show cents-exact allocations, reasons behind the allocations, and simple
  10%, 30%, and 100% risky-asset-decline examples.
- Continue to use only recent scanner / checksum-verified checkpoint names for
  optional experimental stock ideas. These are not verified securities and
  must be explicitly enabled. No fresh scan, market order, or price refresh is
  triggered by the budget calculator.
- Editing any input invalidates the previous displayed result. An earlier
  response arriving after inputs change is discarded.

## Predeclared example weights (not estimated from future returns)

Each entry is **core diversified-market ETF example % / optional satellite %**.
Unallocated balance remains cash. The satellite is used only when enabled and
supported by fresh, eligible stock-name evidence (max 10% per individual stock).

| Horizon | Cautious | Balanced | Growth-oriented |
| --- | --- | --- | --- |
| Within 1 year | 0 / 0 | 0 / 0 | 0 / 0 |
| 1–5 years | 25 / 0 | 35 / 10 | 40 / 10 |
| 5+ years | 60 / 0 | 65 / 20 | 70 / 20 |

The default **5+ years** is only a demonstration starting point, not an
inference about the visitor. The loss limit defaults to *unspecified*, so no
personal dollar-risk constraint is applied unless entered. The engine gives
priority to the diversified core when the loss limit is lower than the target.

**Examples, $100, balanced, no individual-stock opt-in:**
- 5+ years, unspecified loss cap: $65 SPY example / $35 cash
- 5+ years, $20 affordable-loss limit: $20 SPY example / $80 cash
- 1–5 years, no cap: $35 SPY example / $65 cash
- Within 1 year: $0 in stocks, $100 cash

An equity fund may lose most or all of its value; no taxable account, fees,
order restrictions, emergency reserves, inflation, or personal suitability
analysis is modeled. Cash means *unallocated budget*, not a verified deposit
account or promised yield. The 100% scenario is a thought experiment, not a
statistical tail-risk estimate. The historical adjusted-close share estimates
for satellites are **not executable quotes**.

## HTTP contract

`POST /api/research/budget-plan` now optionally accepts:

```json
{
  "budget_usd": "100.00",
  "style": "balanced",
  "horizon": "medium",
  "max_loss_usd": "25.00",
  "allow_experimental_stocks": false
}
```

Backward compatibility: omitting `horizon` selects `long`, and omitting
`max_loss_usd` skips the cap (retains the old 3E.1 $65/$35 example). Max loss
must be in whole cents between zero and the total budget inclusive.

The JSON response adds `horizon`, `max_loss_usd`,
`modeled_risky_principal_usd`, `loss_cap_binding`, `planning_explanations`,
and `stress_scenarios`. Existing fields remain available.

## Apply and test

Apply the ZIP on a new branch from the latest merged main. **Avoid switching
branches during the existing 8:00–9:00 a.m. New York scheduler window**.

Backend:

```bash
cd ~/StockTradingWeb/backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

Frontend:

```bash
cd ~/StockTradingWeb/frontend
pnpm exec vitest run
pnpm lint
pnpm build
```

Manually test `/planner` with $100, long/medium/short horizons, $0/$25/blank
loss caps, opt-in on/off, and a changed input after a result is displayed.
The planned dollar amounts must always reconcile to exactly the entered budget.

## What this does NOT do

The descriptive scanner still has not demonstrated validated predictive skill.
The planner doesn't optimize expected returns, estimate loss probabilities,
validate income/expenses, account for an emergency fund, or offer trade
execution. The ETF is a pedagogical example and not a price-checked personal
recommendation.
