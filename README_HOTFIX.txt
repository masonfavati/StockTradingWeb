Milestone 3D.2 — journal static checks hotfix

Changes limited to 2 source files:
- backend/app/analysis/forward_journal.py: remove unused CalendarError import; avoid reusing `entry` for a date and JournalEntry in capture.
- backend/app/analysis/forward_journal_cli.py: avoid reusing `item` as both JournalEntry and optional JournalEntry across register/capture branches.

No business logic, migration, database, or research records modified.

Apply from repo root:
  unzip -o ~/Downloads/StockTradingWeb_3D2_Journal_Typing_Hotfix.zip -d ~/StockTradingWeb

Verify from backend:
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check

Next test:
  uv run python -m app.analysis.forward_journal_cli register --dir ~/StockTradingWebResearch --record ~/StockTradingWebResearch/forward_20261114_175735.json --expect-checksum 8704c43bc212175139e03a8296f322fbca0391d5214564e1060be1580c92948e
