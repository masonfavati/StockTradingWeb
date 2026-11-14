STOCKTRADINGWEB — MILESTONE 3D.2: FORWARD RESEARCH JOURNAL
===========================================================
APPLY ON: feature/forward-research-journal from freshly merged origin/main
FILES: 5 new files (2 Python application, 1 test, 1 docs, 1 README)
MIGRATIONS: none
EXISTING FILES MODIFIED: none

New commands:
  uv run python -m app.analysis.forward_journal_cli register --help
  uv run python -m app.analysis.forward_journal_cli capture --help
  uv run python -m app.analysis.forward_journal_cli status --help

Read docs/MILESTONE_3D2_FORWARD_JOURNAL.md for exact steps to pin your
existing November 14 record, check PENDING status and try duplicate-safe capture.

macOS/Linux only for the local fcntl advisory lock in this milestone.
Manual invocation only: installing a recurring scheduler is a separate step.
No background process, stock orders, forecasts, or performance claims.

Validations in reconstructed local harness: 23 new tests passed and
183 tests in available reconstructed project passed. The full 236-test
merged repository, Ruff, mypy, and PostgreSQL Alembic checks must be run
by the user locally after applying the patch.
