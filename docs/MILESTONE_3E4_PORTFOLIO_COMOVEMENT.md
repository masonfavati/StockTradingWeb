# Milestone 3E.4: Historical portfolio co-movement (first phase)

## Purpose

Add an **optional, user-triggered** historical correlation review of experimental
stock ideas that already passed 3E.3's name, liquidity, price, volatility and
drawdown screens. No verified issuer IDs, official industries/sectors, forecasts,
orders, or database migrations are introduced.

## What changes

- `/planner` adds **Require historical co-movement evidence**, checked by default
  once experimental stocks are enabled. The experimental-stock opt-in itself
  remains OFF by default.
- With both switches enabled, `POST /api/research/budget-plan` may make one bounded
  Alpaca historical SIP request for **SPY plus at most two candidate symbols**;
  it never starts a full-market scan. With the switches disabled the existing
  budget flow makes **zero extra historical requests**.
- Requests split/dividend-adjusted daily bars (`adjustment="all"`) through the
  scanner's historical signal date, no later. Requires 61 SPY sessions, all 61
  corresponding sessions for a stock, and 60 finite, varying daily log returns.
- Stock pairs with Pearson correlation >= 0.80 are not both included in an
  example allocation. A high SPY correlation is displayed as context, not used
  as a categorical rejection rule. No factor/sector/issuer correlation is
  inferred.
- Failed provider requests, missing SPY data, gaps in stock prices, duplicate
  dates or invalid core prices do not produce guessed correlations. Affected
  stock dollars are kept as cash and the failure is disclosed.
- Show retrospective portfolio annualized volatility and peak-to-trough
  drawdown for a fixed-share **hypothetical portfolio formed using today's
  selected stocks**. This suffers from selection-in-hindsight bias and is NOT
  a historical trading strategy result or a predicted loss distribution.
- Keep 3E.2's nominal affordable-loss cap, 3E.3's 10% stock cap and baseline
  ETF allocation. A rejected stock's originally proposed dollars are NEVER
  redistributed to surviving stocks after the correlation review.

## Research limitations

This is a bounded, retrospective diagnostic, not portfolio optimization or
verified investment guidance. 60 paired return observations are short and
can lead to unstable correlations; industry relationships and legal issuer
identities remain unverified. SPY's asset type is not an up-to-date broker
eligibility check. Historical `all` adjusted prices are revised retrospectively.
No timely executable share prices, spreads, dividends beyond the adjusted
return convention, taxes, brokerage constraints, or trade orders are modeled.

If a user chooses to disable the correlation requirement, legacy 3E.3
examples can still show individual-stock slices, explicitly without an
observed pairwise-correlation safeguard.

## Reproducible manual checks

1. With experimental stocks OFF, create a $100 Balanced/5+ years scenario:
   original illustrative core/cash split, no extra historical data call.
2. Turn experimental stocks ON and leave historical co-movement ON:
   a recent completed scanner snapshot and 3E.3 quality-approved candidates
   are needed. Observe an adjusted-price comparison (or a transparent
   unavailable/missing-history explanation with the stock slice as cash).
3. Turn the correlation requirement OFF: existing 3E.3 quality rules apply.
4. Set maximum affordable loss to $20 and try medium/short horizons; check
   the exposure limit and exact-cent budget reconciliation still hold.
5. Change a control: the previous budget result must disappear.
6. Confirm no modifications to `~/StockTradingWebResearch`, scheduler,
   database, or market trades.

Backend: `uv run pytest -q && uv run ruff check . && uv run mypy app && uv run alembic check`
Frontend: `pnpm exec vitest run && pnpm lint && pnpm build`
