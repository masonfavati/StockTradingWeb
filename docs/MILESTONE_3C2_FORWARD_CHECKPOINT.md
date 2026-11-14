# Milestone 3C.2 — Prospective research checkpoint

**Purpose:** Save the existing **market-wide** scanner's descriptive top-20 shortlist **before** the future holding-period outcome is known. This adds a basic forward-research audit trail, **not** validated trading probabilities, buy signals, or orders.

## Run

Ensure `backend/.env` contains rotated, private Alpaca credentials. No real-money order is sent.

```bash
cd ~/StockTradingWeb
mkdir -p ~/StockTradingWebResearch
cd backend
uv run python -m app.analysis.forward_cli \
  --out ~/StockTradingWebResearch/forward_$(date +%Y%m%d_%H%M%S).json \
  --horizon 20
```

Run on a completed-data day, *before the next intended entry session*. This performs a complete new provider scan of the current active-tradable asset directory, instead of using the limited previously backfilled sample. It may take time and use many requests within the free Alpaca limits. Stop if the provider rejects a request. Never falsely label a partial scan as complete.

**Output:** a new private JSON file, deliberately **not in the Git repository**, including observed UTC timestamp, verified latest completed market session, observed coverage, eligible-universe SHA-256, exact initial top-20 rankings, a hypothetical next-session opening entry, and a chosen holding period. If the provider's results are incomplete or stale, no record is saved. Files cannot be overwritten by this command. Store the JSON in a safe place for future evaluation.

**Caution:** This command uses SIP `all` adjusted prices that are available *when the scan runs*. This is acceptable as a frozen **future-facing** research observation, but does not make prior adjusted bars point-in-time accurate. The current scanner's research score is not a calibrated forecast, probability, or buy recommendation. This patch also does **not** yet fetch future outcomes, adjust executions for corporate actions, resolve delisting proceeds, or fix classification of warrants/ETFs/units. A recorded hash and local timestamps are not independent trusted timestamps. Do not backdate runs.

For a hypothetical entry at the *next* eligible NYSE session open and an exit 20 additional sessions later, the comparison can only be calculated after that future exit has actually occurred. Avoid interpreting any forward test that starts before the record was created as valid.

This does not replace Milestone 3C.1's readiness safety gates, which correctly block historical uses of the November 14, 2026 universe snapshot on earlier replay dates.
