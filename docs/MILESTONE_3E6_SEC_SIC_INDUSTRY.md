# Milestone 3E.6 — SEC SIC issuer-industry evidence

The optional Budget Planner industry screen uses the **SEC submissions** `sic` and `sicDescription` metadata for the **issuer/filer CIK** matched by the earlier 3E.5 ticker cross-reference. It does NOT infer classifications from ticker suffixes, ticker names, or ETF holdings.

## What this feature does

- Requires explicitly enabled experimental stocks and SEC filer identity matching before adding an SIC screen.
- Compares up to two prequalified experimental stock ideas. If both filers report the **same SIC code**, only the first can receive the proposed stock allocation; the second's allocation remains **cash**.
- Missing SEC identity, missing SIC, stale reference (over 30 days), corrupt snapshot, mismatched reference digest, or ambiguous ticker: **no speculative dollars allocated** for affected investments.
- Reports the actual SIC code and SEC `sicDescription` for each considered ticker and the reasons for exclusions.
- Respects existing budget, maximum affordable loss, short investment horizons, historical-quality checks, and the optional co-movement screen. It does not make trades or change research predictions.
- Doesn't request SEC data over the network during budget planning.

## Two ways to set up SEC SIC data

Both need the **3E.5 SEC ticker–CIK reference** imported in `~/StockTradingWebResearch` first:

```bash
cd ~/StockTradingWeb/backend
uv run python -m app.market_data.sec_identity_cli status --dir ~/StockTradingWebResearch
```

### Option A: Small files for the companies you want to evaluate (recommended for most users)

First, find the CIK URLs for one or two tickers, e.g.:

```bash
uv run python -m app.market_data.sec_industry_cli urls \
  --dir ~/StockTradingWebResearch \
  --symbol AAPL --symbol MSFT
```

The tool prints the SEC's exact official per-company `https://data.sec.gov/submissions/CIK##########.json` URLs using the pinned 3E.5 ticker reference. Download each source JSON file from the printed URL to your Mac, then import all files **in one command**:

```bash
uv run python -m app.market_data.sec_industry_cli import-files \
  --dir ~/StockTradingWebResearch \
  --source ~/Downloads/CIK0000320193.json \
  --source ~/Downloads/CIK0000789019.json
```

Those filenames are examples for the illustrative tickers. The importer matches the **CIK inside each SEC JSON file** to the pinned ticker reference; it does not trust the filename alone. You may pass 1–30 files in one import. `import-files` creates a **new compact reference** covering *only those CIKs*, not the whole market. An optional industry check for any other CIK remains unavailable and leaves its proposed stock dollars in cash. To replace the entire import later, pass **all desired files together** with `--replace`; this does not silently append or refresh old metadata.

### Option B: Whole SEC submissions archive (for broad coverage)

The SEC also publishes the **bulk submissions.zip**, recompiled nightly:

https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip

**This is a very large download (roughly 1.5 GB at the time of writing); it is NOT required for the small-file route.** Do not unzip it: the importer reads the ZIP in place, extracts only SIC fields for the pinned ticker–CIK list, and writes a small local reference.

```bash
uv run python -m app.market_data.sec_industry_cli import \
  --source ~/Downloads/submissions.zip \
  --dir ~/StockTradingWebResearch
```

Archive entries with unsupported/missing SIC metadata, or individual member files over the per-member limit, aren't used; the status output counts oversized members.

### Check the import

```bash
uv run python -m app.market_data.sec_industry_cli status \
  --dir ~/StockTradingWebResearch
```

A pinned local industry reference lives in `~/StockTradingWebResearch/reference/sec_sic_reference_v1.json` with a content digest and import timestamp. Keep it outside git. Update SEC ticker–CIK and SIC references deliberately; if the ticker reference changes, old SIC evidence is not considered a matching source until reimported.

## Browser usage

Open `/planner`, enter a dollar budget, enable **experimental individual-stock ideas**, then enable **Require SEC SIC industry evidence**. This automatically activates and locks the **SEC filer cross-reference** requirement. The planner displays the resulting SIC classifications and any rejected allocations. `Require historical co-movement evidence` remains a separate optional check. If neither of the proposed tickers has a usable matching SIC import, the planner displays a reason and keeps their dollars as cash.

## Important limits

- SIC describes a **current SEC filer-level classification**. It does not establish that a specific ticker is a common share, nor map to the market sectors used by GICS/ICB or to a company's revenue mix. Two companies with different SICs may have highly correlated businesses; two with the same SIC may have diverse products.
- This is **not point-in-time history**. Do not use today's SIC metadata to reconstruct industries known at an earlier signal date or claim validated past strategy performance.
- The SEC data is public but imports are local and timestamps/hashes are **not independently certified**. Downloaded files could be incomplete, and import time alone is not the SEC publication time.
- The index is an **input-quality safeguard**, not a predictor of future returns or a substitute for proper portfolio-level correlation analysis.
- Baseline allocations for SPY and cash are still illustrative, not broker quotes or investment recommendations.

Official documentation: https://www.sec.gov/search-filings/edgar-application-programming-interfaces
