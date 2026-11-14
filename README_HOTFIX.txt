StockTradingWeb — Milestone 3C.2 malformed-opening-price hotfix

Apply only while on feature/backtest-readiness, after the 3C.2 forward-checkpoint patch.

This archive replaces:
  backend/app/market_data/history_client.py
  backend/app/analysis/market_scan.py
  backend/app/analysis/forward_record.py
  backend/app/analysis/forward_cli.py
  backend/app/api/scanner.py
and adds:
  backend/tests/test_scanner_invalid_core_quarantine.py
  docs/MILESTONE_3C2_INVALID_CORE_HOTFIX.md

No database changes, no credentials, no saved market data, and no generated JSON research records are modified.

Before applying, check your branch and archive contents:
  git branch --show-current
  unzip -l ~/Downloads/StockTradingWeb_3C2_Core_Bar_Quarantine_Hotfix.zip

Apply from repository root:
  unzip -o ~/Downloads/StockTradingWeb_3C2_Core_Bar_Quarantine_Hotfix.zip -d ~/StockTradingWeb

Verify from backend:
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

Then retry the forward scan with a new, unique research-record filename.
