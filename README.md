# StockTradingWeb

A **free, local stock-market research website** that helps people explore US stocks without needing to understand trading jargon.

It's a work in progress. You can follow companies, monitor limited real-time market activity, save real historical price data, and now **search Alpaca's broad active-tradable US-stock list for research candidates**. It includes a prospective prediction research lab and a new **visual growth workspace** that explores historical-pattern forecasts and bounded, illustrative dollar allocations. The model is *not prospectively validated*; none of these estimates is a reliable buy recommendation. The site can also track manual purchases, sales, and review alerts. It cannot guarantee returns, identify the perfect sell point, or place trades.

## What can you do today?

| Feature | What it means |
| --- | --- |
| Dashboard | View the incoming price feed and whether it's live, stale or simulated. |
| Stocks I'm Following | Search by company name, save companies, and monitor your chosen stocks. Adding a company **does not buy it**. |
| Find Opportunities | Click a button to screen Alpaca's active/tradable US stocks using **completed historical daily prices**, even stocks outside your watchlist. This is an **unvalidated research shortlist, not a buy list**. |
| Historical data | Import raw and current-adjusted daily prices from Alpaca into PostgreSQL. |
| Audit | Check saved raw prices for missing market sessions and invalid records. |
| Forecast Lab | Audits frozen prospective scans against matured future outcomes, evaluates a time-safe conditional model, and withholds model picks until research gates pass. Initial status may be insufficient evidence. |
| Visual growth planner (`/`) | Enter a budget, compare historical-pattern growth estimates, see a visual allocation, and optionally explore small, diversified experimental stock positions. |
| My Holdings (`/portfolio`) | Record your actual purchases, sales, fees, and split adjustments; refresh last completed daily prices and review risk rules. Never places trades. |

### Important market-data distinction

- **Live IEX:** With free Alpaca credentials, the application can monitor up to 30 selected symbols from the **IEX exchange only**. These aren't all US-exchange trades or a consolidated best price.
- **Historical SIP:** Broad-exchange daily records, subject to Alpaca's free plan's **latest-15-minutes restriction**. Our importer/scanner deliberately uses completed days, not live prices.
- **Adjusted history:** The `all` series reflects split/dividend/spin-off adjustments known **today**. It is useful for descriptive research but must **not** be mistaken for information available to someone trading years ago.
- **Simulated:** The Alpaca test feed is synthetic. Never treat it as real market information.

## Run the website on your computer

These steps are for **macOS Terminal**, with the repository cloned to `~/StockTradingWeb`. You do **not** need a paid Alpaca plan.

### 1. Install the prerequisites once

- [Docker Desktop](https://www.docker.com/products/docker-desktop/) (start Docker Desktop before opening the website)
- [Python 3.14 or newer](https://www.python.org/downloads/)
- [uv](https://docs.astral.sh/uv/getting-started/installation/) (Python package manager)
- [Node.js 24](https://nodejs.org/)
- [pnpm](https://pnpm.io/installation) (JavaScript package manager)
- A **free Alpaca paper-trading account** to load real data. Do not use live-money trading keys.

If you've already installed these tools, you can skip this step.

### 2. Set up configuration once

Open Terminal and run:

```bash
cd ~/StockTradingWeb/backend
cp .env.example .env
```

Open the new private configuration file:

```bash
open -e .env
```

For real price history and the market-wide scanner, enter **your own paper-account** `ALPACA_API_KEY_ID` and `ALPACA_API_SECRET_KEY` values in that file. Don't share them, paste them into ChatGPT, or put them in `.env.example`. The site can start without Alpaca keys, but real market features need them.

To monitor real IEX prices, also set:

```dotenv
MARKET_DATA_ENABLED=true
MARKET_DATA_FEED=iex
```

If you are just exploring the UI without live streaming, keep `MARKET_DATA_ENABLED=false`.

**Security:** If you previously committed a real API key to this public repository (including an older version of `.env.example`), **revoke/rotate it in Alpaca**. Removing it from the current file does *not* remove it from Git history.

### 3. Start the database (Terminal window 1)

Make sure Docker Desktop is running. Then:

```bash
cd ~/StockTradingWeb
docker compose up -d db
```

This starts a local PostgreSQL database on port **5433**. Your data is saved in a Docker volume between restarts.

### 4. Start the backend API (Terminal window 2)

Open a *second* Terminal window:

```bash
cd ~/StockTradingWeb/backend
uv sync --locked
uv run alembic upgrade head
uv run uvicorn app.main:app --reload --port 8000
```

Leave this window open. `uv sync` installs backend dependencies, `alembic` updates the database structure, and `uvicorn` starts the API at **http://127.0.0.1:8000**.

You can view interactive API documentation at **http://127.0.0.1:8000/docs**.

### 5. Start the website (Terminal window 3)

Open a *third* Terminal window:

```bash
cd ~/StockTradingWeb/frontend
pnpm install --frozen-lockfile
pnpm run dev
```

Leave it open, then open **http://localhost:5173** in your browser. That's the **actual website**, not a test runner.

### 6. Use Find Opportunities

In the website, choose **Find Opportunities** from the navigation and click the button.

The server loads the full active/tradable US-equity universe from Alpaca and requests batches of completed, corporate-action-adjusted SIP daily candles. The job can take time because it checks **many stocks**, not just the companies you're following. The page shows progress and a **research shortlist** with one-month and three-month past price changes and a measure of price volatility.

This is **not** a verified strategy, forward return forecast, or likelihood of profit. The ranking is a transparent recent-performance/risk heuristic. No trading occurs. Scans are held in this server process and reused for 15 minutes after completion. Restarting the backend clears the scan result.

Some Alpaca-listed securities can be excluded because they are untradable, have invalid/unhandled symbols, lack enough history, have stale prices, or don't meet initial liquidity/volatility/positive-trend filters. **The screen is not a guarantee that the highest-ranked stock is best.**

### 7. Download and audit historical data (optional)

From `~/StockTradingWeb/backend`:

```bash
# Fetch raw data for stocks in your saved watchlist:
uv run python -m app.market_data.history_import sync --incremental --start 2022-01-01

# Fetch full corporate-action-adjusted research series separately:
uv run python -m app.market_data.history_import sync --adjustment all --start 2022-01-01

# Review stored series:
uv run python -m app.market_data.history_import status

# Check the completeness/integrity of stored raw history:
uv run python -m app.market_data.history_audit
```

The first-ever `--incremental` import pulls full history for a new symbol; for an existing symbol it refreshes only a recent overlapping window. Adjusted history needs periodic **full refreshes**, because corporate actions can change previous adjusted prices.

### Shut everything down

- In the **frontend** and **backend** Terminal windows, press **Ctrl+C**.
- To stop PostgreSQL without deleting its data, run `cd ~/StockTradingWeb && docker compose stop db`.
- **Do not run `docker compose down -v`** unless you want to erase the saved database volume.

## If something isn't working

| Problem | What to try |
| --- | --- |
| Docker can't start the database | Open Docker Desktop and rerun `docker compose up -d db` from the repository root. |
| Website doesn't load | Make sure the `pnpm run dev` window is still running; open the local URL it prints. |
| Website can't reach the backend | Make sure `uv run uvicorn ...` is running on port 8000. Open `http://127.0.0.1:8000/api/health` and check for `{"status":"ok"}`. |
| Scan fails / shows no real data | Verify paper Alpaca credentials in **backend/.env**. Check that Alpaca's API is available. The scanner won't fabricate prices. |
| Historical SIP gives HTTP 403 | A free account cannot request recent consolidated SIP data. Use the importer/scanner's completed-day cutoff; do not manually request right up to the current time. |
| No live trade updates | Markets may be closed, the stream may be disabled, or there may be no IEX trades for the symbol. Check its status indicator instead of treating missing data as $0. |
| Backend says a module is missing | Run `uv sync --locked` in `backend` and try again. |

## Run the automated quality checks (developers)

These commands **test the project**, rather than start the website:

```bash
cd ~/StockTradingWeb/backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

In another Terminal:

```bash
cd ~/StockTradingWeb/frontend
pnpm exec vitest run
pnpm run lint
pnpm run build
```

## What's next?

The current scanner is only the first step. The goal is to estimate expected risk-adjusted returns across the broader market using **point-in-time data, realistic transaction costs, walk-forward testing, and well-calibrated uncertainty**. Until that evidence exists, we will **not** label any candidate as a confident buy or promise the "best" investment. We also need proper financial-fundamental data to assess whether a company is genuinely cheap relative to its business, not merely cheap per share.

See [`docs/PROJECT_CONSTITUTION.md`](docs/PROJECT_CONSTITUTION.md) and [`docs/MILESTONE_3B_SCANNER.md`](docs/MILESTONE_3B_SCANNER.md) for engineering details and limitations.

*StockTradingWeb is research software. Prices and forecasts are uncertain. No real-money trading is implemented.*
