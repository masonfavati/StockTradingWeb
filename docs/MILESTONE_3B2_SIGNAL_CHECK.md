# Milestone 3B.2 — Honest historical signal check

StockTradingWeb now has a first **read-only diagnostic** for its market scanner's existing trend/volatility score. It does **not** place trades, produce a profit probability, or claim the strategy is valid.

## What this does

For each non-overlapping evaluation date:

1. Read **only Alpaca SIP `raw` daily bars already stored in PostgreSQL**. Never use the `all`-adjusted series for historical signals: it includes revisions known today.
2. Require 61 consecutive recorded market sessions per stock ending on the signal day, then reuse the current scanner's fixed filters and score using information through that day only.
3. Select the highest-ranking `--top` candidates **before looking at their later prices**.
4. Assume a signal formed *after the close* on the evaluation date and a hypothetical buy no earlier than the **next market session's opening price**. A hypothetical sell uses an opening price after the specified number of additional sessions. Apply an assumed per-side trading cost to both the selection and its comparison.
5. Compare the selected stocks with an equally weighted basket of **all locally tracked symbols that had complete historical input windows at the time of the signal**, not with a total-market benchmark. Missing future prices invalidate a trial; no higher-ranked substitute may be chosen with hindsight.
6. Report the count of signal dates, evaluated windows, samples with missing future prices, average window price changes, and how often the selected candidate beat the saved-universe basket.

A **positive** average does not prove a strategy works or that its future profit probability is high. The current scanner's rules were not developed independently from this history, and the local universe is tiny and chosen today; therefore the results suffer from selection/survivorship bias.

## How to apply the patch

The patch ZIP contains **only new paths**, so it does not overwrite your running scanner, API, README, database, credentials, or existing tests. In the repository root:

```bash
unzip -l ~/Downloads/StockTradingWeb_3B2_Signal_Validation.zip
unzip -o ~/Downloads/StockTradingWeb_3B2_Signal_Validation.zip -d ~/StockTradingWeb
```

Run the usual checks from `backend`:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

## Run the research diagnostic (real saved data, no API calls)

Start Docker Desktop and the local PostgreSQL database if necessary:

```bash
cd ~/StockTradingWeb
docker compose up -d db
cd backend
uv run python -m app.analysis.validation_cli --horizon 20 --top 1 --cost-bps 10
```

- `--horizon 20` = evaluate about one trading month's price change after an available next-session opening price, assuming an exit at a later opening price.
- `--top 1` = choose the highest-ranked **eligible stock among the locally saved symbols**, not among the historical full market.
- `--cost-bps 10` = **assume**, rather than observe, 0.10% trading friction on the hypothetical buy **and** on the hypothetical sell.

Try `--cost-bps 25` to see how sensitive the result is to higher hypothetical costs. With the current AAPL, APLE, MSFT dataset, the report should warn that the number of tracked symbols is inadequate for a statistically meaningful market-wide claim. Exact returns depend on the actual saved raw records; no figures are hardcoded or fabricated.

## Crucial limitations and release gates

- **Not a complete historical market universe:** The currently saved stocks cannot represent delistings, inactive former stocks, or companies that were not in the user's watchlist. Results must not be presented as "market-wide backtested".
- **Raw price-only:** Does not model dividends, splits, mergers, spin-offs, borrow fees, or tax effects. Some splits look like enormous price declines. This is **not total shareholder return**.
- **Not an execution simulator:** Open-to-open prices are a timing convention, not guaranteed actual fills. Assumed costs are not measured historical spreads; no partial fills or market impact.
- **No model-selection independence:** The chosen lookback and thresholds aren't yet subject to separate model-selection and untouched out-of-sample evaluation. No calibrated positive-return probabilities exist.
- **Not a portfolio simulation:** Window averages are not compounded portfolio equity, risk-adjusted alpha, maximum drawdown, or investable returns. The simple comparison is a local-universe basket, not SPY or another public benchmark.
- **Calendar completeness:** Locally observed sessions are not a complete historical exchange calendar. The data-quality audit is a separate step.

The follow-up work is to collect an as-of historical universe and point-in-time corporate actions, add actual total-return labels and benchmark, and use a frozen training/evaluation protocol with realistic costs. Until then, the **Find Opportunities** website remains a research shortlist, not a validated recommendation.
