# StockTradingWeb Milestone 3A.3 — Incremental and adjusted history

## Why

The initial importer collected complete **raw** daily SIP bars. This patch lets the
same importer safely update recent raw history without downloading years of
observations, and optionally collect separate corporate-action-adjusted research
series. No paid API, automated trading, new dependency, or database migration.

## Usage (from backend/)

```bash
# Daily updates for existing watchlist symbols: defaults to raw prices,
# and per-symbol overlap with the last seven calendar days.
uv run python -m app.market_data.history_import sync --incremental --start 2022-01-01

# Check raw data remain intact and any additional bases are separately marked.
uv run python -m app.market_data.history_import status

# Separate full-period series adjusted for splits, dividends and spin-offs.
uv run python -m app.market_data.history_import sync --adjustment all --start 2022-01-01

# Verify raw SIP data still agree with the market calendar.
uv run python -m app.market_data.history_audit
```

`--adjustment split` is also available. `raw` remains the default.
`--incremental` is intentionally **raw only**: a new dividend or split may
retroactively change **every earlier** adjusted price, so refreshing only the
most recent week would leave adjusted records internally inconsistent.

A new watchlist symbol imports from `--start`; previously stored symbols
start seven calendar days before their most recent saved session (not before
`--start`). Re-importing is idempotent. The overlap addresses recent gaps and
provider corrections, not every older outage. **Periodically run a full raw
import and the independent calendar audit.** The current CLI must be invoked
manually; it does not run itself in the background.

## Critical financial data constraints

- Raw bars reproduce unadjusted historical market prices and volumes.
- The `all` series uses Alpaca's **present-day** corporate-action adjustments:
  splits, cash dividends and spin-offs. It is a retrospective *research*
  series, not as-observed historical evidence. Its earlier values can change
  after an event; importing it now and treating it as known five years ago
  causes look-ahead bias. Do not use the current `all` series directly as
  point-in-time training features, or to reconstruct historical execution
  prices, brokerage cash flow, tax costs or an individual's actual P&L.
- Adjustment snapshots are updated in place, and `fetched_at` shows the most
  recent retrieval. This patch does **not** persist historical vintages or
  corporate-action announcement-time eligibility. Those are prerequisites
  for strict event-based backtests.
- Coverage before a stock's first observed bar still needs IPO/listing checks.
- This patch does not automatically repair an old missing day or retry 429s.
- Watchlist-only data are not a historical whole-market universe and cannot
  establish absence of survivorship bias.

No actual buy/sell recommendations are produced by these utilities.
