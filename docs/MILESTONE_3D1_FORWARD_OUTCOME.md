# Milestone 3D.1 — Frozen prospective outcome evaluation

This is a **research audit**, not a trading system, return prediction, or backtest of market membership. It evaluates **only the candidates saved at recording time**, never selecting new winners after seeing future prices.

## Key rules

- Takes a frozen `forward_*.json` saved by Milestone 3C.2, and requires its original printed SHA-256 via `--expect-checksum`. The content is verified using canonical JSON, preventing silent modification of the shortlisted securities (a hash stored only inside the same file alone would not suffice).
- Uses the provider's exchange calendar through the conservative last-completed-session cutoff. **20-session horizon = next session's opening entry plus an exit at the open 20 exchange sessions later**, requiring 21 future exchange sessions, not 20. Does not retrieve future outcome prices or write an audit while the exit date is still pending.
- Rejects a checkpoint not demonstrably recorded before the proposed next-session open. It conservatively requires the checkpoint's *New York date* to precede the entry session date (same-day-before-open checkpoints are not evaluated by this version).
- Fetches **Alpaca SIP split-adjusted daily opens** up to the frozen exit session (not through any later evaluation date), using only entry and exit observations. Adjustments are used for **outcome accounting**, never to recreate or change the original signal. This is not a true fill price, and does not model dividends, cash corporate actions or delisting proceeds.
- Uses **SPY** as the predeclared benchmark and **10 basis points per side** as an example predeclared friction assumption. If you change this assumption, the outcome JSON records the actual choice; don't optimize after seeing results.
- If **any** frozen candidate or SPY lacks a valid entry or exit open, or has malformed/duplicate bars, **the portfolio comparison is withheld**; per-stock diagnostics remain available. Stocks are never replaced by hindsight winners.
- Writes a new, private, non-overwritable JSON audit, with its own SHA-256 digest and the source checkpoint digest. It never edits the original checkpoint. Provider errors stop the run instead of fabricating results.
- One market-wide checkpoint of twenty chosen assets is still **one selection event**, not twenty independent experiments and not a proven predictive strategy.

## Start a new feature branch

```bash
cd ~/StockTradingWeb
git fetch origin
git switch -c feature/forward-outcome-evaluation origin/main
```

Apply the patch ZIP at the repository root, then run the normal backend checks.

## Check status now (no outcome prices fetched)

```bash
cd ~/StockTradingWeb/backend
uv run python -m app.analysis.evaluate_forward_cli \
  --record ~/StockTradingWebResearch/forward_20261114_175735.json \
  --expect-checksum 8704c43bc212175139e03a8296f322fbca0391d5214564e1060be1580c92948e \
  --status-only
```

This should report PENDING until the frozen exit session has completed and the conservative SIP cutoff has passed. The evaluation date is obtained from the actual exchange calendar, rather than estimated by counting calendar days.

## When the holding period has completed

```bash
cd ~/StockTradingWeb/backend
uv run python -m app.analysis.evaluate_forward_cli \
  --record ~/StockTradingWebResearch/forward_20261114_175735.json \
  --expect-checksum 8704c43bc212175139e03a8296f322fbca0391d5214564e1060be1580c92948e \
  --out ~/StockTradingWebResearch/outcome_$(date +%Y%m%d_%H%M%S).json \
  --cost-bps 10
```

The command will not create an outcome JSON if the exit hasn't yet matured. After maturity it downloads only the frozen selections and SPY, then creates a diagnostic JSON. A complete equally weighted return and SPY comparison appears only when **every** entry and exit open is available and valid.

## Known limitations and future 3D work

This version assumes equal-weight, fractional-share purchases and no rebalancing during the horizon. The friction assumption is illustrative, and quotes/spreads at market open are not available from daily bars. Split adjustments do not cover dividends or delisting settlements. Security types were not verified by the original scan. Local hashes and timestamps are not independently trusted provenance. Evaluate **many** precommitted scan dates and improve corporate-action and execution accounting before making any claim about expected returns or profit probability.
