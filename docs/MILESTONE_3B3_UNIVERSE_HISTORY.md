# Milestone 3B.3 — Universe capture and bounded historical coverage

## What this adds

This is the first **prospective** market-universe archive. Alpaca's US equity asset directory is saved as a dated PostgreSQL snapshot, recording Alpaca's stable asset identifier, symbol, exchange, name, active/inactive state and tradability. Snapshots are captured only for the actual New York calendar date; existing dates are not overwritten.

The backfill CLI uses **only the active/tradable stocks in a saved snapshot** as its stock list, rather than the three stocks in the watchlist. It requests **real raw completed-day SIP history** in batches and saves with the established idempotent historical-bars importer.

**Important limitation:** A snapshot captured in November 2026 does not reveal the investable market in January 2022. A broad backfill based on today's surviving stocks is still subject to survivorship, delisting, universe-selection and changed-ticker bias. This work does not validate the scanner's profitability or furnish a point-in-time backtest. It does not add automatic trading, new subscriptions, or a historical corporate-action ledger.

## Safe install

From the repo root:

```bash
unzip -l ~/Downloads/StockTradingWeb_3B3_Universe_History.zip
unzip -o ~/Downloads/StockTradingWeb_3B3_Universe_History.zip -d ~/StockTradingWeb
```

**Alembic registration, once:** Run this small, guarded helper from the repository root:

```bash
python3 tools/register_universe_model.py
```

The helper changes only the existing model import in `backend/alembic/env.py`. If that import differs from the expected one, the helper stops without editing it; inspect the file rather than forcing a replacement. The included migration revises `7724bc191cdd`; verify `uv run alembic heads` before upgrading. If your migration head is different, stop and reconcile the chain before applying it.

```bash
cd ~/StockTradingWeb/backend
uv run alembic upgrade head
uv run alembic check
uv run pytest -q
uv run ruff check .
uv run mypy app
```

## Use (with the backend installed and Docker database running)

```bash
cd ~/StockTradingWeb
docker compose up -d db
cd backend
uv run python -m app.market_data.universe_history capture
uv run python -m app.market_data.universe_history status
```

Check the printed stock counts before backfilling. Capturing the same New York date again reuses the existing record instead of overwriting it.

**Small smoke test: 20 stocks, 90 days of raw history.** Change the start date as appropriate (must be at least one completed day ago):

```bash
uv run python -m app.market_data.universe_history backfill --start 2026-08-01 --limit 20 --batch-size 10
```

Then process another non-overlapping range:

```bash
uv run python -m app.market_data.universe_history backfill --start 2026-08-01 --offset 20 --limit 20 --batch-size 10
uv run python -m app.market_data.history_import status
```

`--offset` and `--limit` refer to alphabetically sorted, snapshot-eligible symbols and are intentionally explicit. Check the **Next offset** line for the next invocation. A failed batch prints its offset so you can retry. Previously completed pages are safely upserted, but *a failed run is not an all-or-nothing transaction*. The provider may have no history for a listed symbol, in which case no bar is fabricated. Retain the snapshot and use the same `--snapshot YYYY-MM-DD` for consistent offsets across different days.

The default request pace is conservative but does not guarantee avoidance of shared-account rate limits. If you get HTTP 429, stop and retry later at the failed offset. No paid plan is required. Each invocation is deliberately bounded to at most 500 selected symbols.

## Validation caveats

- The stock directory is **not** an authoritative historical listing and delisting ledger.
- Delisted, bankrupt, merged, renamed and OTC stocks require additional point-in-time research.
- Current raw daily prices are not adjusted total returns; splits and dividends still need care.
- All comparisons must use only information actually available at the decision timestamp.
- The frontend's market-wide scan is unchanged by this patch.
