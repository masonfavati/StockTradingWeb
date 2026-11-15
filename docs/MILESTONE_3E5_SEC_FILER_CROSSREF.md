# Milestone 3E.5 — Official SEC ticker–filer cross-reference (opt-in)

## Why this exists

The previous name-only apparent-issuer screen is not a legal identity check. A free U.S. SEC public reference associates a **ticker** with a **CIK (filer identifier)**, a filing name and an exchange. This helps catch **multiple stock symbols tied to the same filer**, or cases where a ticker cannot be found in the official SEC table. The public SEC file is documented at:

- https://www.sec.gov/file/company-tickers-exchange
- https://www.sec.gov/files/company_tickers_exchange.json

**SEC ticker–CIK association does not certify common-stock status, issuer ownership, industry/sector, price, suitability, or future return.** The SEC table also contains some exchange-traded products and non-common instruments. Therefore this is only an **additional opt-in guard after** the existing common-name, liquidity, volatility and drawdown screens. It does not change or rewrite historical scanner checkpoints.

## One-time free local setup

1. Open the official SEC Company Tickers Exchange page above and download `company_tickers_exchange.json` using your web browser. The file is public; no subscription or API credentials are required for this manual download.
2. From the repository's `backend` directory run:

   ```bash
   uv run python -m app.market_data.sec_identity_cli import \
     --source ~/Downloads/company_tickers_exchange.json \
     --dir ~/StockTradingWebResearch
   uv run python -m app.market_data.sec_identity_cli status \
     --dir ~/StockTradingWebResearch
   ```

3. Open the Investment Planner, enable **experimental individual-stock ideas**, and optionally enable **Require SEC filer cross-reference**. Only if **both** are on will the API read this locally imported reference. There are no per-request SEC network calls.

To refresh the reference later, download a new SEC file and run the same import with `--replace`. It is deliberately explicit; no silent overwrite. The local copy lives at `~/StockTradingWebResearch/reference/sec_ticker_reference_v1.json`, outside Git, with import time, source-URL metadata, the SHA-256 of the downloaded source, and a local consistency checksum. These local checksums **are not digital SEC signatures or independently certified timestamps**. The original SEC file does **not** provide a publication timestamp, so import date cannot establish actual data freshness.

The opt-in refuses a locally imported reference older than 30 days. Stale, corrupt, absent, ambiguous, unsupported-exchange, or unmatched entries are excluded from the **experimental stock slice only**; their money stays as cash. The broad-market ETF core is still an unverified illustrative choice. No paid API is needed, and no orders are placed.

## What happens when both SEC and historical co-movement checks are requested?

The planner first applies existing name and historical-quality filters to a maximum of two experimental stock candidates, then cross-checks the proposed tickers against the locally pinned SEC reference. Proposed shares of the same SEC CIK are not both allocated. Only surviving symbols enter the optional historical co-movement analysis. A rejection at either stage **does not redistribute that stock's original dollar slot** to the survivor; the remainder stays in cash.

## What remains out of scope

- SEC CIK is a **filer identifier**, not a unique security identifier such as a verified share-class instrument identity. The same filer can have different classes, ADRs, rights, or warrants.
- SEC company names can differ from Alpaca security names; we show both without automatically declaring a mismatch proof.
- Ticker punctuation is intentionally **not guessed** (e.g. `BRK-B` is not silently equated with `BRK.B`).
- The reference is **current**, not proof of who held a ticker on earlier research dates.
- **Industry/sector is unknown** in this reference. A later milestone can add SEC submissions SIC (separately documented), historical identity changes, authoritative security-type data, and sector-specific exposure limits. We must not label a ticker as sector-diversified from this table alone.
- SEC absence or ambiguity does not imply an investment is inherently bad; it means our optional evidence requirement cannot support its allocation.

## Validation

Run the two full suites before merging:

**Backend:**

```bash
cd ~/StockTradingWeb/backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

**Frontend:**

```bash
cd ~/StockTradingWeb/frontend
pnpm exec vitest run
pnpm lint
pnpm build
```

Test `$100`, Balanced, 5+ years, with and without the SEC toggle. Without a reference, enabling the toggle leaves all experimental stock dollars as cash. With an imported reference, matched distinct SEC filers can receive those small allocations if they pass the existing screens. Confirm the affordable-loss limit and optional co-movement still apply. Test an import refresh only when you deliberately want to replace the pinned file.
