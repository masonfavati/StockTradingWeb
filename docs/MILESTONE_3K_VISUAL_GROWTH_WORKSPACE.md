# Milestone 3K — Visual Growth Workspace & Manual Holdings

**One integrated patch. No additional paid vendor, database migration, brokerage API, or automatic trade execution.**

## The new experience

- **Home (`/`)**: Enter a budget, investment horizon, affordable loss limit, and approach; select **Build my investment picture**. The home screen now leads with a dollar-allocation wheel, ranked estimates, uncertainty bars, and a chart with an explicit past/future boundary.
- **Discover without a prior click**: The planning button first tries a *fresh* full-market shortlist from a completed website scan or a verified research journal. If none exists, it starts the existing market-wide scan and displays progress, then obtains **independent completed daily historical bars** for at most 11 qualifying candidates plus SPY. The scan can take many minutes or fail due to free-provider limits. No provider request occurs merely from opening home.
- **Compare your own stocks**: An optional comma-delimited ticker list (up to 10) evaluates only those stocks and SPY. This is **not** a market-wide ranking. Because arbitrary tickers have not passed the full-market security-type screen, this route displays forecasts **but cannot assign experimental stock dollars**.
- **Growth models**: 1-, 3-, and 6-month endpoints correspond to 20, 60, and 120 completed trading sessions. The model finds comparable *past* price patterns using recent momentum, volatility, and historical drawdown. It only trains on returns matured by each test origin, compares held-out absolute errors against a simple historical-mean baseline, and reports nonoverlapping test-window counts and past-pattern gain frequency.
- **Dollar plan**: A constrained illustrative comparison considers forecast growth *and* historical downside, uncertainty, and pairwise correlations. It compares up to four-stock subsets; with sparse price overlaps it refuses to guess diversification. It limits individual-stock allocations to 10% per ticker and keeps unallocated dollars in cash. Core SPY exposure, stock caps, short-horizon cash preference, and the affordable-loss principal cap are retained. **Individual stocks appear in a dollar scenario only after explicit experimental opt-in.**
- **History + estimates**: The solid line shows actual historical adjusted daily prices. A *separate* shaded range and point show an experimental endpoint only. **No intermediate future price path is predicted.**
- **Holdings (`/portfolio`)**: A local manual journal records purchases, partial sales, fees, and manual share-count adjustments for splits. It calculates remaining holdings using FIFO cost and realized profit/loss on recorded sales. The user can undo only the most recent transaction. Records persist under `$STW_RESEARCH_DIR/manual_portfolio_v1.json` (default `~/StockTradingWebResearch/manual_portfolio_v1.json`) with restricted file permissions and atomic replacement.
- **Review alerts**: On opening a nonempty holdings page or clicking **Update values and review risks**, the app fetches completed *raw* daily prices, estimates holding values, and checks predefined thresholds: recent price drop of 12% from a 60-session high, recorded position down 15% from its cost, or a position above 30% of a completely valued portfolio. Alerts do not sell anything. Data gaps are displayed as gaps.

## What this does NOT establish

1. **No validated accuracy claim.** The exploratory model uses historical data on today's currently selected/surviving stocks and corporate-action adjustments known today. This is affected by selection, survival, ticker reuse, and corporate-action hindsight. Even an improved walk-forward historical error is not a reliable out-of-sample *prospective* result. Continue the existing genuine forward journal for independent validation. No forecast is a guaranteed probability, confidence interval, peak, or future price path.
2. **No real-time trading quotes.** Forecasts use the Alpaca SIP historical daily feed on completed days. Portfolio updates use completed daily **raw** closes. Neither is a buyable or sellable price. The provider's free plan may restrict recent data and request volume.
3. **No broker account connection or trade execution.** Users must input actual fills and fees. Share splits require an explicit share adjustment; otherwise quantity/basis and valuations can be wrong. Dividends, taxes, brokerage cash, and external transactions are not imported. Realized gains are **not tax reporting**.
4. **No exact market-timing promise.** Thresholds may warn late or falsely; a stock can gap down before a warning, and stop-loss instructions would not guarantee execution at any level. Review notices are *not* automatic sell advice.
5. **Not a global mathematical optimum.** A bounded, risk-penalized comparison among up to 11 eligible current shortlist members or user-supplied tickers is not an exhaustive search of all market securities, and historical correlations are unstable. A core allocation uses transparent capped presets rather than optimized future returns.
6. **Local-only personal holdings.** Portfolio API endpoints reject non-loopback callers. This is a single-machine local product, not a multi-user secure hosted service. Do not expose the app publicly without authentication, HTTPS, backups, and authorization controls.

## Backend verification

From `~/StockTradingWeb/backend`:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

## Frontend verification

From `~/StockTradingWeb/frontend`:

```bash
pnpm exec vitest run
pnpm lint
pnpm build
```

## Manual acceptance tests (browser)

1. Load `/` and verify no historical API request or expensive scan starts *until* **Build my investment picture** is clicked.
2. Enter `$100`, Balanced, five-plus years. Calculate with experimental allocations disabled. Confirm the allocation wheel and cash exactly total $100, and no individual stock buy recommendation is issued.
3. Turn experimental stock allocations on and calculate. Check that stock exposure is small and capped, the model is labeled experimental, and cash retains refused allocations.
4. Open one ranked stock. Check actual past prices are visually separated from the estimated *endpoint*, with the future band labeled **not guaranteed**. Try different budgets, time frames, and loss caps.
5. If no fresh market shortlist exists, the single button should start a normal full-market scan and show truthful progress. Alternatively, use the advanced ticker box (e.g. `AAPL, MSFT`) to test independent price history without rerunning the market-wide scan. Actual availability depends on Alpaca.
6. Open `/portfolio`, record a BUY with a date, shares, price and fee. Confirm it survives page reload, then record a smaller SELL. Verify the remaining shares and realized P/L.
7. Press **Update values and review risks** (the page will also refresh nonempty positions on opening). Verify only completed-day prices are shown, and the review state is not a command to sell. If prices fail, the ledger should remain intact.
8. Attempt to sell more shares than recorded. It should fail without modifying the portfolio. Undo the latest transaction and confirm records recalculate.
9. Confirm previous pages (`/history`, `/forecasts`, `/planner`, `/decisions`, `/compare`) still load. There is no database migration.

### Historical model limitations worth testing over time

The key research question is **whether prospective predictions on frozen signals actually beat a naive broad-market holding and simple historical baselines**. Do not remove the preexisting 3F prospective validation gate, or use an unvalidated 3K ranking to bypass it in the older Investment Planner.
