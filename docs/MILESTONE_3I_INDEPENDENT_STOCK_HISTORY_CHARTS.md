# Milestone 3I — Independent Stock History Charts

**One complete patch; no database migration; no paid services.**

## Why

The Decision Desk and Find Opportunities screens previously published aggregated scanner metrics. These are historical, but they are not a browseable price history. The new **Stock History Charts** page (`/history`) lets users inspect actual independently retrieved daily bars for any syntactically valid US ticker, with no scanner run or saved research checkpoint required.

## How it works

- **Backend:** `GET /api/research/stock-history/{symbol}?period=1y&compare_spy=false` uses the existing `AlpacaHistoryClient.pages` implementation and Alpaca's historical **SIP daily** feed. One ticker at a time; optional SPY benchmark. Periods: 1 month, 3 months, 1 year, 5 years (bounded approximate calendar windows). Prices are `adjustment=all` (corporate actions known today). History currently covers dates since 2016 where the provider supports them.
- **Freshness:** the requested endpoint ends conservatively at 23:00 New York time on the **previous local calendar day**; today's potentially incomplete candle and the Basic-plan latest-15-minute restriction are never presented as completed data. Actual last recorded bar date and data-retrieval timestamp are shown.
- **Data integrity:** invalid ticker formats are rejected. Invalid/duplicate dates, unexpected tickers, nonpositive/nonfinite prices, future and incomplete sessions, too many pages, and excessively large responses fail closed. There is no zero-price placeholder. Missing benchmark dates are never filled: comparison uses **only sessions where both instruments have real bars**. Both indexed lines start at 100 on the same anchor date.
- **Rate limits:** at most 12 cache-miss chart requests per backend process per minute, at most six vendor pages and 3,400 bars per request, with a ten-minute bounded in-memory successful-response cache (64 entries). Historical data errors return generic 503 messages without exposing broker credentials or provider response details. Multiple backend processes maintain independent rate budgets; this is not a distributed production rate limiter.
- **Frontend:** `/history` has ticker search, selectable 1M/3M/1Y/5Y ranges, daily adjusted closing-price graph, SPY normalized-performance toggle, historical session inspector accessible by keyboard, period change summary, dates/source/cutoff caveats, and a vertical scanner-date marker when arriving from a scan or Decision Desk. It is linked directly from the scanner, Decision Desk, planner allocations, and navigation.
- **No fictional forecast:** 3F's current model estimates conditional probability of beating SPY over 20 trading sessions, **not a future dollar price or path**. The chart says why no projection is available; `price_forecast` is explicitly `null`. We must NOT extrapolate or draw a future curve from the probability. A real forward path would require a separate point-in-time trained and independently calibrated price/return distribution with uncertainty and holdout validation.

## Setup

Existing Alpaca API credentials in `backend/.env` are required. No new keys, subscriptions, background processes, migrations, or files on disk. The historical bar endpoint is called **only when the user visits a history page or switches periods/comparison**; the rest of StockTradingWeb does not make new requests.

## Two quality suites

Backend (from `backend`):

```bash
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

Frontend (from `frontend`):

```bash
pnpm exec vitest run
pnpm lint
pnpm build
```

## Manual acceptance checks

1. Open `/history` directly without clicking Find Opportunities (defaults to SPY). Observe genuine older sessions and a price graph; no scan should start.
2. Enter `AAPL` or a candidate ticker. Switch 1M, 3M, 1Y, and 5Y; verify the dates, chart, period change, and freshness label are consistent.
3. Toggle **Compare with SPY**. The chart switches from adjusted dollars to aligned indexed values. Missing SPY dates must be dropped, never estimated.
4. Move the historical-session slider with keyboard or pointer and verify the displayed date and adjusted close change.
5. From `/scanner` or `/decisions` click **View historical price chart** and confirm the selected ticker and scanner-date marker. From `/planner`, click **View independent price history** next to a ticker allocation.
6. Enter an invalid ticker and observe a friendly validation error; try a supported ticker with no provider history and observe an honest empty state, not a fabricated zero line.
7. Read the prediction section. It MUST explain that the existing 20-session model predicts relative SPY outperformance, **not a projected share price**. No future line should appear unless a separately validated price model is eventually built.
8. The current Forecast Lab, budget planner, risk gates, and market scanner must remain unchanged functionally.

## Known limitations

- This visualizes retrospective `adjustment=all` series. These are not exact prices that could have been traded on historic days, nor safe point-in-time feature inputs for historical model training.
- Ticker renames and identifier reuse are NOT resolved by this chart endpoint; the existing SEC references are separate and do not fix price-series identity changes.
- A successful historical price chart does **not** mean an instrument passes SEC identity, industry, liquidity, correlation, or prediction evidence gates.
- Prices are **not** executable or intraday quotes, and the comparison is not a total-return portfolio backtest.
- 3F training still uses *frozen prospective scanner inputs and independently matured outcomes*. This milestone intentionally does not backfill synthetic historical predictions or claim predictive skill from retrospective curves.

Official Alpaca references: https://docs.alpaca.markets/us/reference/stockbars and https://docs.alpaca.markets/us/docs/about-market-data-api
