# Milestone 3A.1 — Free daily price-history ingestion

This stage collects real historical stock prices into PostgreSQL. It does not make investment recommendations.

## Data integrity

- Source: authenticated Alpaca historical stock bars, `feed=sip` by default.
- Free Basic access allows historical consolidated SIP data older than 15 minutes; this is **not a real-time quote**. Live IEX monitoring stays separate.
- Frequency: `1Day` daily bars, not intraday or real-time.
- `adjustment=raw`: do not calculate historical returns across splits or dividends until corporate-action handling has been implemented.
- `asof=-`: never silently rewrite ticker identities across name changes. This initial importer does not yet solve symbol history, delisting, or survivorship bias.
- Only completed New York trading sessions are stored. Current-session partial bars are excluded.
- Missing, unexpected, or invalid provider data results in explicit errors, never simulated replacements.
- Decimal-valued OHLC/VWAP and an idempotent composite key preserve price precision and prevent duplicate days. Vendor corrections update previously saved observations; **predictions must be stored separately and immutably**.
- Imports are rate-limited to fewer than 200 requests per minute. The free tier and data licensing should be rechecked before public deployment.

## Setup

1. Unpack new files at repository root on a new branch.
2. In `backend/alembic/env.py`, add `historical_bar` to the existing `from app.models import ...` import. Do not delete `instrument` or `watchlist`.
3. Start Docker: `docker compose up -d db`.
4. Generate and review a new Alembic migration (it should **only add historical_bars**):
   `uv run alembic revision --autogenerate -m "create historical daily bars"`
5. Apply migration: `uv run alembic upgrade head`.
6. Check quality: `uv run pytest -v`, `uv run ruff check .`, `uv run mypy app`, `uv run alembic check`.
7. Import your saved watchlist (backend `.env` requires Alpaca keys):
   `uv run python -m app.market_data.history_import sync --start 2022-01-01`
8. Display progress: `uv run python -m app.market_data.history_import status`
9. Re-run `sync` to verify idempotency; stored-day totals should remain stable.

## Limits

- No charts or financial recommendations yet. The importer is an engineering foundation, not a trading signal.
- Data is initially for watched stocks, **not the entire available market**. Later scanner milestones will batch a much larger universe with exchange and historical-listing awareness.
- Daily bars are derived summaries; they are not complete trade-by-trade records or a substitute for live quotes.
- In local development this executes on-demand. Scheduling and backfill audit/reporting come later.
