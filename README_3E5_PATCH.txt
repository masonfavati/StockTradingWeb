StockTradingWeb — Milestone 3E.5 / Optional SEC ticker-to-filer evidence

Apply this ZIP to the root of a fresh feature branch based on merged main.
This ZIP contains only the 11 files listed by unzip -l and no API credentials or database migration.

The official SEC company_tickers_exchange.json is NOT bundled or fetched automatically.
Download it directly from https://www.sec.gov/file/company-tickers-exchange
and import with the CLI described in docs/MILESTONE_3E5_SEC_FILER_CROSSREF.md.

This is an opt-in CIK issuer cross-reference, NOT verified instrument class,
sector, valuation, expected profitability, or trading advice.

Run complete backend and frontend quality suites on the actual repository.
