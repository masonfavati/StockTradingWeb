# Milestone 3D.3 — optional macOS scheduled research collection

## Scope, guarantees, and prerequisites

This patch wraps the already-tested 3D.2 journal's **`capture`** operation. It adds an **opt-in macOS LaunchAgent** and an operational attempt log. No trades, order access, backdating, outcome computation, new scoring rules, or database migration.

A complete scanned checkpoint is still registered only if the *existing journal* validates the independent exchange calendar, unique (signal/rule/horizon) key, original checksum, scan completion time, and before-entry eligibility. Failure to contact Alpaca or to complete the scan produces a failed scheduler attempt **without an invented research record**. The journal's file lock prevents concurrent duplicate captures. Trading days missed because the Mac was asleep, off, offline, or without valid Alpaca credentials are genuine **missing observations**, not retrospectively replayed selections.

**Scheduling strategy:** LaunchAgent wakes the program hourly at :15 according to macOS local time. The Python wrapper performs **no provider request outside 08:00–08:59 America/New_York**, regardless of the Mac's timezone or daylight-saving changes. Only one invocation on an awake Mac normally falls in that hour. This is a *local user-session* schedule, not a 24/7 cloud service. On scheduled wake from sleep, launchd may invoke a delayed task; the Python time gate and journal rules then decide whether capture is still permitted. No automatic backfill or retry of expired signal dates.

**Research timing:** The existing conservative price cutoff uses the previous New York **calendar** day. This patch also tightens and aligns capture/evaluation rules to allow a next-session morning checkpoint **only if the entire scan completes before 09:00 New York time** (30 minutes before the regular 09:30 US equity open). Thus Tuesday at 08:15 can capture Monday's completed signal, and Monday at 08:15 can capture Friday's, provided all checks pass. Previously, the evaluator disallowed even a properly timed same-day-before-open checkpoint; this patch fixes that inconsistency. If the scan finishes at or after 09:00, its output is retained for inspection but **never registered**. Holidays may yield duplicate skips instead of new predictions. A hypothetical open fill is NOT guaranteed in actual trading.

## Branch and patch

```sh
cd ~/StockTradingWeb
git fetch origin
git switch -c feature/scheduled-forward-research origin/main
# Unzip 3D.3 patch at the repository root
cd backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

## Verify the schedule before enabling it

Use your existing private research directory:

```sh
cd ~/StockTradingWeb/backend
uv run python -m app.analysis.forward_schedule_cli plan --dir ~/StockTradingWebResearch
```

The `plan` output shows the literal LaunchAgent settings. In particular verify `ProgramArguments` points to `~/StockTradingWeb/backend/.venv/bin/python`, **not** `/Library/Frameworks/Python.framework/...` (the system interpreter), `WorkingDirectory` to `~/StockTradingWeb/backend`, and that the research path is correct. The virtual-environment executable is often a symlink to the system interpreter, but the *launcher path must not be resolved*: invoking the link is what activates the virtual environment. If the plan rejects the interpreter, run `uv sync` from `backend` and retry. It does **not** install anything.

On **macOS only**, create (but do not activate) the plist:

```sh
uv run python -m app.analysis.forward_schedule_cli write-plist --dir ~/StockTradingWebResearch
```

This refuses to overwrite an existing plist. If you need to change the environment, deactivate and remove the old plist manually after backing it up, then create a new one. It stores **no Alpaca credentials**; the subprocess loads `backend/.env` in the configured working directory. The Python path in the plist must remain available after upgrades. Your Mac must be running and your user session must be active for regular execution.

Enable manually (explicit opt-in):

```sh
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.stocktradingweb.forward-research.plist
```

See the loaded service:

```sh
launchctl print gui/$(id -u)/com.stocktradingweb.forward-research
```

Disable it:

```sh
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.stocktradingweb.forward-research.plist
```

To permanently remove scheduling, run the `bootout` command before removing the plist. Existing research checkpoints and attempt logs are **never** automatically removed. Do not use `launchctl kickstart` to force a scan at the wrong time: the New York time gate will skip it.

## Test and monitor

Outside 08:00–08:59 Eastern, a manual invocation prints `SKIPPED: outside ...` and uses **no Alpaca requests**:

```sh
uv run python -m app.analysis.forward_schedule_cli run-once --dir ~/StockTradingWebResearch
```

Inside the morning window, the wrapper delegates to 3D.2's `capture`: this can perform a full ~13,500-symbol Alpaca scan, unless the journal reports a duplicate or a late signal. Ensure your plan's API rate limits are respected, and do not run multiple separate research directories or machines against the same account concurrently.

See the last 10 eligible-time attempts (pure local read, no data-provider requests):

```sh
uv run python -m app.analysis.forward_schedule_cli log --dir ~/StockTradingWebResearch
```

Operational logs, including stdout and stderr from the full scan, live under `~/StockTradingWebResearch/operations/`. Check `launchd.stderr.log` if an unattended attempt failed. A JSONL attempt log records timestamp, action state, and checksum for successfully registered checkpoints. This is **not a trusted independent timestamp**, and a pending scan is not evidence of future returns. Don't commit any logs, checkpoints, or API secrets to Git.

**Important:** leave the Mac awake with network access near 08:15 Eastern, or accept that some signal dates will be missed. `launchd` is not a guaranteed cloud scheduler. You can disable the agent whenever you like. The journal and existing outcome evaluator still operate separately.
