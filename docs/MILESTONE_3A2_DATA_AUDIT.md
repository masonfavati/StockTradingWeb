# Milestone 3A.2 — Permanent Historical-Data Audit

The read-only command `uv run python -m app.market_data.history_audit` checks Alpaca SIP **raw** daily bars in PostgreSQL against Alpaca's market calendar through the latest completed New York calendar day.

Checks:
- Missing completed exchange sessions after each symbol's first recorded trading date, **including missing recent dates**.
- Saved dates not on the exchange calendar.
- Invalid OHLC price relationships and negative volumes.
- Raw day-to-day closing-price jumps >=30%, reported as **warnings**, not assumed corrupt data.

The audit does **not** prove the first stored day is the first day the stock traded, that exchange calendar values are independently verified outside Alpaca, or that raw historical prices represent investment total returns. Corporate actions (splits, dividends, spin-offs) still need adjustment before forecasting returns. Newly listed, halted, delisted, or otherwise nontrading securities may require special handling.

The command requires the same free Alpaca credentials as the historical importer. It does not mutate the database and does not initiate trades.

Exit codes: 0 = checks passed; 1 = audit findings/no rows; 2 = calendar verification unavailable or invalid.

For future model work, archive input data timestamps and versions, and avoid using retroactively adjusted prices without point-in-time discipline.
