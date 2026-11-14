# Milestone 3B.3 — Transparent research-name screens (patch)

Alpaca labels a very broad collection of securities `us_equity`. An `active` and `tradable` security may still be an ETF, warrant, unit, right, preferred stock, or depositary receipt. Alpaca's asset-directory response does not certify an exact ordinary/common security type for every ticker. **No name-only filter can certify eligibility or predict profits.**

This patch adds read-only screening profiles over the **saved** snapshot; no new provider subscription, database migration, data deletion, or automatic purchase. It deliberately leaves `--profile all` as the **default**, with precisely the same alphabetical ordering and offsets used by your completed first 100 symbols.

## Commands

From the repo root, inspect and apply the patch on `feature/universe-history`:

```bash
unzip -l ~/Downloads/StockTradingWeb_3B3_Security_Screens.zip
unzip -o ~/Downloads/StockTradingWeb_3B3_Security_Screens.zip -d ~/StockTradingWeb
cd ~/StockTradingWeb/backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

Report the captured directory's candidate types without modifying anything:

```bash
uv run python -m app.market_data.universe_history profiles --snapshot 2026-11-14
```

The report prints counts of names with evidence of common shares, warrants/rights, units, preferreds, funds/ETPs, depositary shares, and unclassified/missing names. **These are text heuristics, not verified security classifications.** Descriptions such as “Class B” without “common” stay unclassified, rather than being invented as common shares.

Profiles, each with a **different offset sequence**:

- `all` (default): original active/tradable symbol-compatible list. The original offset **100** remains valid here.
- `exclude-obvious-complex`: removes identifiable warrants/rights, units, preferreds, funds/ETPs, depositary receipts, or missing names. **Unclassified names remain, and may still be complex securities.**
- `common-name-evidence`: accepts only names explicitly containing “common stock,” “common shares,” or “ordinary shares,” after excluding obvious complex terms. This is intentionally narrow and will exclude some legitimate stocks.

For profiles other than `all`, duplicates of the same ticker from different asset IDs are excluded to avoid ambiguous identity. This may reduce coverage.

To continue **the existing all-symbol run** from the previous next-offset 100:

```bash
uv run python -m app.market_data.universe_history backfill \
  --snapshot 2026-11-14 --profile all \
  --start 2026-08-01 --offset 100 --limit 50 --batch-size 10
```

For a *separate* filtered experiment, **begin at offset zero** for that profile. Never reuse offset 100 from `all`:

```bash
uv run python -m app.market_data.universe_history backfill \
  --snapshot 2026-11-14 --profile common-name-evidence \
  --start 2026-08-01 --offset 0 --limit 20 --batch-size 10
```

Every profile report and backfill prints a **fingerprint**, which marks the snapshot date, profile, screening implementation version, and ordered symbol list. When resuming, pass the matching value via `--expected-fingerprint <value>` to stop *before downloading* if the list changes. Keep the fingerprint with the offset when recording progress.

**Financial integrity:** these name screens are not point-in-time historical membership. Current tradability, prices, exchange listing, corporate actions, and ticker identity must still be validated independently before investment research can inform actionable decisions. Newly added price history doesn't mean earlier historical scanner backtests are free from selection bias. VWAP `NULL` counts and prices must continue to be audited separately. The current front-end scanner's ranking method is **unchanged** by this patch.
