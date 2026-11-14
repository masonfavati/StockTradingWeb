# Milestone 3B — First all-market research screen (NOT a predictor)

## Requirement

A watchlist is not the investing universe. The user wants a **one-click** discovery workflow scanning available Alpaca equities and eventually recommending investments, not merely comparing three manually watched symbols.

## Implemented now

- `GET /api/scanner/status` and `POST /api/scanner/scan` (one server-process background task; 15-minute completed-job cache).
- Directory: Alpaca active US equities, `tradable=true`, valid symbols, not the watchlist. Reports eligible universe size.
- Completed-day historical SIP bars, `adjustment=all`, 180-calendar-day lookback, 60-symbol requests, 10,000 bars/page, pagination and conservative request pacing.
- A transparent preliminary screen requiring 61 daily observations, adjusted close >= $2, approximate 20-day traded value >= $1 million/day, annualized volatility between 0 and 120%, and positive 60-session change.
- Descriptive ordering by 60-session price change divided by annualized historical volatility. Displays actual lookback changes and risk measures.
- No investments bought or sold; no prediction, confidence score, or proof that top result will outperform.
- A readable UI at `/scanner` with progress/status, ranking limitations, and no stale result from partially failed scans.
- README with actual database/backend/frontend startup instructions and no credentials in `.env.example`.

## Critical limitations / future work

1. **No expected return model or profitability probability.** Screening thresholds are illustrative, not fitted or independently backtested. The ordering is a risk-adjusted *historical* metric, not a price prediction.
2. **No point-in-time universe.** Today's Alpaca active asset list excludes historical delistings: any backtest using this list uncritically has survivorship bias.
3. **Current `all` adjusted history is not point-in-time.** Adjustments from later corporate actions can leak into old backtests. Do not train/score historical simulations without as-of-aware snapshots.
4. **A low share price or large drawdown is not evidence of an undervalued business.** No fundamental data or fair-value model is included.
5. **Liquidity estimates are approximate.** Adjusted close * recent volume is a screening heuristic, not a historical transaction simulator.
6. **Stale and absent bars.** Assets can be skipped for missing provider data, IPO history, halts, and filter failures. Coverage is explicitly reported; avoid implying Alpaca has full consolidated live coverage on its free plan.
7. **Local single-process runner.** Scan status/results reset if the backend restarts; not suitable for multiple worker instances or a hosted public service. Large scans can last minutes.
8. **Incomplete real-time monitoring.** Free IEX streams are limited; scan uses completed-day SIP only and must not be called a real-time market-wide scan.
9. **No online ingestion/scheduling.** Run per explicit button click, with 15-minute cache. No automated trading.
10. **Validation roadmap:** historically accurate asset membership, point-in-time fundamentals, out-of-sample walk-forward evaluation, realistic costs/spreads/slippage, calibrated risk of loss, benchmark comparisons, and reliable abstention ("no trade") decisions.

## Checks

From backend: `uv run pytest -q && uv run ruff check . && uv run mypy app && uv run alembic check`

From frontend: `pnpm exec vitest run && pnpm run lint && pnpm run build`

Browser: Start Docker, backend, frontend per README; press **Find Opportunities** and verify progress, broad universe count, completed-day labels, and no ranking after provider failure. No API credentials should ever enter client-side JavaScript.
