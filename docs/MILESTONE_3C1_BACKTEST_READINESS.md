# Milestone 3C.1 — Market-wide backtest readiness audit

This is a **read-only coverage and temporal-integrity audit**, **not** a trading
strategy, a profitability forecast, or a full backtest. It adds no tables and
makes no changes to saved historical prices or directory snapshots.

## Why it exists

The Alpaca directory snapshot was captured on **2026-11-14**, while the original
backfilled raw price history currently ends **2026-11-13**. Using a directory
observed on November 14 to decide which securities were eligible in August
would use **future knowledge**. No number of clean-looking price bars fixes that.

Moreover, the current scanner's ranking needs **61 historical sessions**.
Testing a **20-session** holding period also requires a following opening
session and an exit opening session: at least **82 consecutive exchange sessions**
per complete replay window (61 + 1 + 20). An approximately 74-session data
window from August to mid-November is therefore too short even for one full
20-session replay. Earlier symbols with five years of prices can have sufficient
rows but are *still* not historically eligible under a later snapshot.

The audit distinguishes:

1. A **capture date** (what the provider reported when you actually saved it).
2. A **profile** chosen using descriptive name-based heuristics, not a certified
   instrument type.
3. **Raw SIP price-date coverage** for a bounded subset, compared with the real
   exchange calendar retrieved from Alpaca's free calendar API.
4. **Contiguous lookback/replay window sufficiency** (only enough data to attempt
   a replay, not evidence of a sound historical strategy).
5. An explicit **as-of date gate**: a captured directory is never considered
   known on an earlier date, or even the same date when decision timestamps are
   not available.

## Apply and test

Create a fresh feature branch from `origin/main`; extract the patch at the repo
root. Then from `backend`:

```sh
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

## Audit the data imported so far

Start Docker/PostgreSQL if necessary, then:

```sh
cd ~/StockTradingWeb

docker compose up -d db
cd backend

uv run python -m app.analysis.readiness_cli \
  --snapshot 2026-11-14 \
  --profile common-name-evidence \
  --start 2026-08-01 \
  --end 2026-11-13 \
  --offset 0 \
  --limit 100 \
  --horizon 20
```

This samples **the first 100 symbols of the 3,289-symbol profile**; it does
**not** claim the remaining symbols were audited. You can inspect a different
slice with `--offset 100 --limit 100`. Limits are capped at 500 to prevent an
unbounded query. No stock order or price data is modified.

The report should reveal that the November 14 snapshot cannot be validly used
for August–November 13 historical trading decisions. If the sample spans ~74
exchange sessions, none can furnish a complete 82-session 20-day replay window
within that interval. A later snapshot can only support decisions *after* the
snapshot was genuinely captured, with additional safeguards for price
availability and stale listings.

## Operational and scientific limitations

- Snapshot asset statuses are observed **prospectively**, not historically
  reconstructed, even for inactive securities in the directory.
- Price history is downloaded later and can be retroactively corrected. The
  database `fetched_at` field is not proof that a prior trader saw that value.
- Classification profiles are based on security names; they can exclude good
  stocks or include unsuitable securities.
- A missing opening-day price may indicate a new listing; this audit reports
  missing data, not an automatic provider defect.
- Raw daily bars omit dividends, delisting proceeds, realistic corporate-action
  treatment, spreads, slippage, cash and position sizing.
- An asset ID is more stable than a reused ticker, but the price table is still
  keyed by ticker/date, so ticker-reuse history needs separate treatment.
- This report never claims a model is accurate, profitable, or ready for real
  investment recommendations.

## Next engineering steps

Capture **new** directory snapshots regularly, start recording provider receipt
metadata on historical prices and later model decisions, research delisted and
reused ticker identities, extend coverage, and develop a frozen out-of-sample
walk-forward evaluation. Validate those safeguards before presenting
market-wide forecast probabilities or profitable-buy rankings.
