# Milestone 2C.3 — Beginner-first watchlist

## What this patch adds

- New **Stocks I'm Following** page at `/watchlist`.
- Search for U.S. companies by **name or symbol** using the authenticated, free Alpaca `/v2/assets` directory.
- Search results come from provider records; no invented company names. Results are cached in memory for one hour to avoid unnecessary API calls.
- Follow/remove companies using the existing persistent watchlist API; removing a company from the watchlist **does not sell shares**.
- New `/api/market/monitored/events` SSE endpoint streams every monitored stock, without opening a new Alpaca connection per browser tab.
- Plain-English messages distinguish *demo*, *live IEX*, *stale*, *not subscribed*, and *feed unavailable*.
- Disclose 30-symbol free-feed limit and IEX-only live coverage.

## New endpoints

- `GET /api/watchlist/search?q=apple` — requires your existing paper API credentials; returns up to 12 verified matches.
- `GET /api/market/monitored/events` — streams a full market-monitor snapshot every second.

Existing `GET /api/watchlist`, `POST /api/watchlist`, `DELETE /api/watchlist/{symbol}`, `GET /api/market/status`, and `GET /api/market/events` remain unchanged.

## Local test checklist

1. Start PostgreSQL (`docker compose up -d db`), FastAPI (`uv run uvicorn app.main:app --reload --port 8000`), and Vite (`pnpm run dev`).
2. Open `http://localhost:5173/watchlist`.
3. Search **Apple**, choose **Follow**, and confirm Apple appears in **My saved companies**.
4. Refresh the page: Apple should remain saved.
5. Search **Microsoft**, follow it, then verify `/api/market/monitored` includes both symbols when IEX mode is enabled.
6. With `MARKET_DATA_FEED=test`, no real company should display a simulated FAKEPACA price.
7. With `MARKET_DATA_FEED=iex`, quotes appear only after actual IEX events; outside trading activity the app may correctly show *waiting*.
8. Remove a company; the saved list updates and no trade or order is placed.
9. Run backend `uv run pytest -v`, `uv run ruff check .`, `uv run mypy app`, `uv run alembic check`.
10. Run frontend `pnpm exec vitest run`, `pnpm run lint`, `pnpm run build`.

## Known limitations

- **Local single-user only.** Do not expose write endpoints on a public host until authentication and per-user ownership are implemented.
- IEX is not a complete U.S. consolidated market feed; displayed prices are not guaranteed executable prices.
- Prices are observations, not forecasts or buy/sell recommendations.
- The backend currently chooses the first 30 watchlist symbols alphabetically; priority for owned holdings requires the future portfolio ledger.
- The collector runs inside a single FastAPI process. Do not scale to multiple API workers yet.
- No new database migration is required by this patch.
