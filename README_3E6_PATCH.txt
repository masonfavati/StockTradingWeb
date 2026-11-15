StockTradingWeb Milestone 3E.6 — SEC SIC industry evidence

Apply only after 3E.5 is merged. Create a feature branch from origin/main, then:
  unzip -o ~/Downloads/StockTradingWeb_3E6_SEC_SIC_Industry_Evidence.zip -d ~/StockTradingWeb

Backend suite (your Mac):
  cd ~/StockTradingWeb/backend
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

Frontend suite (your Mac):
  cd ~/StockTradingWeb/frontend
  pnpm exec vitest run
  pnpm lint
  pnpm build

See docs/MILESTONE_3E6_SEC_SIC_INDUSTRY.md for BOTH setup options.
The per-company SEC submissions files are small; the bulk ZIP is optional and very large.

No database migration, API keys, background installation, automatic trades, or
changes to your existing LaunchAgent. SIC is issuer-level classification,
NOT a certified share type, sector diversification model, or return forecast.
