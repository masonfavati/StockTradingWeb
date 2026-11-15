StockTradingWeb 3D.3 — LaunchAgent Python environment hotfix

Problem: the schedule preview resolved a virtualenv Python symlink to the global
Frameworks interpreter. When launchd invokes the global interpreter, it may
not find project dependencies installed inside backend/.venv.

Solution: explicitly select the active virtualenv bin/python, preserve its
symlink spelling in the plist, and refuse schedule setup from global Python.
The hourly :15 launchd wakeup and 08:00–08:59 New York-time gate are unchanged.
No live scanning, Alpaca contact, launchd installation, or trading is triggered.

Files: backend/app/analysis/forward_schedule.py,
       backend/tests/test_forward_schedule.py,
       docs/MILESTONE_3D3_SCHEDULED_RESEARCH.md

Verify using uv run pytest -q, uv run ruff check ., uv run mypy app,
and uv run python -m app.analysis.forward_schedule_cli plan \
  --dir ~/StockTradingWebResearch

Do NOT activate launchd unless the preview points inside backend/.venv/bin.
