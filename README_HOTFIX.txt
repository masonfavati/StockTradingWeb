StockTradingWeb Milestone 3B.3 — Historical VWAP Parser Hotfix

Problem:
  A real Alpaca backfill stopped on "Invalid VWAP value in provider data."
  Our previous parser rejected an entire historical page if any non-null
  volume-weighted average price (VWAP) was zero, negative, or malformed.

Policy:
  - Always reject bad timestamps, OHLC prices, negative volume, and unknown symbols.
  - Accept a null/absent VWAP, as before.
  - If a non-null VWAP is unusable, save NULL for VWAP only, and retain validated
    OHLCV fields, trade count, and date. Never substitute a price or estimate.
  - Report the number and example symbol/date of VWAP anomalies per page in a
    WARNING, without copying the provider's untrusted raw values into logs.
  - This is an ingestion-quality workaround, not a claim that Alpaca's VWAP was valid.
  - The database schema already makes VWAP nullable; no migration is needed.

From repository root, on feature/universe-history:
  unzip -l ~/Downloads/StockTradingWeb_3B3_VWAP_Hotfix.zip
  unzip -o ~/Downloads/StockTradingWeb_3B3_VWAP_Hotfix.zip -d ~/StockTradingWeb

Then in backend:
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check
  uv run python -m app.market_data.universe_history backfill --start 2026-08-01 --offset 0 --limit 20 --batch-size 10
  uv run python -m app.market_data.history_import status

If another error occurs, stop and report it instead of ignoring it.
Any earlier completed batches were preserved. Repeating offset 0 is idempotent.
