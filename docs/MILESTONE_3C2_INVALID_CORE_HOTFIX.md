# Milestone 3C.2 — Malformed core-price quarantine for screening

## Why this exists

The market-wide Alpaca `all`-adjusted daily-bar response contained an invalid **opening price** after thousands of successfully queried symbols. The old client rejected the page and stopped the whole scanner. Invalid OHLCV is not equivalent to invalid optional VWAP: essential opening/high/low/closing/volume fields cannot be invented or null-filled for return estimates.

## Behavior after this patch

- **Strict historical imports remain strict.** `AlpacaHistoryClient.pages()` defaults to raising on invalid core OHLCV or missing/invalid timestamps. It continues to reject unexpected symbols, malformed response shape, and provider/authentication errors.
- **The market-wide scanner uses `screening_pages()`.** It records the symbol, date where recoverable, and general validation reason; discards the damaged daily record and **quarantines the entire affected symbol from ranking**, including any otherwise-valid bars from other pages.
- Each scan records `excluded_invalid_core_symbols`, `invalid_core_records`, and up to five sanitized examples; these become fields and warnings in the prospective JSON checkpoint. The scanner website shows the excluded-symbol count in its completion message.
- The scan still cannot succeed on provider failures, unexpected symbols, malformed response structures, or incomplete pagination. A fully queried market with some transparently excluded securities is not claimed to have complete usable OHLCV for every ticker.
- Optional bad VWAP continues to be stored as NULL in strict imports; no prices or returns are fabricated.

## What isn't solved

- Candidate score is still exploratory, not a calibrated probability of profit or a trading recommendation.
- This is not a point-in-time historical market-universe reconstruction.
- Excluding damaged securities reduces usable coverage and could introduce selection bias. The checkpoint records exclusions; future evaluation must use this metadata, not ignore it.
- Some legitimate trading suspensions or corporate actions can also create unusual observations and need separate investigation.
- A failed forward scan does not have a resumable progress checkpoint. Retrying performs a fresh full scan; do not reuse a partial ranking.

## Verification

From `backend`:

```bash
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

The patch adds 14 parser, scanner, provider, and checkpoint regression cases. No migration is needed.

Then retry a **new filename** (never overwrite prospective evidence):

```bash
mkdir -p ~/StockTradingWebResearch
uv run python -m app.analysis.forward_cli \
  --out ~/StockTradingWebResearch/forward_$(date +%Y%m%d_%H%M%S).json \
  --horizon 20
```

If it succeeds, inspect `excluded_due_to_invalid_core_bars`, `invalid_core_bar_records`, and `invalid_core_examples` in the saved JSON and keep the file private. A file hash is not an independent trusted timestamp.
