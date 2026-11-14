# Milestone 3D.2 — prospective research journal and once-per-signal capture

**Purpose:** Build a trustworthy series of forward selections, not a profitable-strategy claim. This is deliberately **not** an automatic trading or background scheduling service.

This additive patch introduces `app.analysis.forward_journal_cli` with three commands:

- `register`: pin the SHA-256 **printed at the time of an earlier scan** to the original checkpoint, without modifying it.
- `capture`: run the existing whole-market Alpaca scanner only when a complete prior exchange session can be verified **and** the next exchange session has not yet arrived. Only one checkpoint per signal session + scanner rule + horizon is registered. Repeat invocations skip the expensive scan. No checkpoint is backdated.
- `status`: verify all pins and source hashes, then compare sessions completed with each frozen horizon using the independently retrieved exchange calendar. No outcome prices are fetched.

## Create a branch after merging 3D.1

```sh
cd ~/StockTradingWeb
git fetch origin
git switch -c feature/forward-research-journal origin/main
```

Extract the patch ZIP into the repository root, then from `backend`:

```sh
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

## Register your existing November 14 checkpoint first

The existing checkpoint remains where it is. No scanning or price downloads are involved in registration.

```sh
cd ~/StockTradingWeb/backend
uv run python -m app.analysis.forward_journal_cli register \
  --dir ~/StockTradingWebResearch \
  --record ~/StockTradingWebResearch/forward_20261114_175735.json \
  --expect-checksum 8704c43bc212175139e03a8296f322fbca0391d5214564e1060be1580c92948e
```

It should print `REGISTERED` with signal `2026-11-13`, horizon `20`, and the original SHA-256. A second identical `register` is an idempotent `ALREADY REGISTERED`.

```sh
uv run python -m app.analysis.forward_journal_cli status \
  --dir ~/StockTradingWebResearch
```

Until 21 future exchange sessions are complete, it should report `PENDING`. This means **no performance claim**; `READY` later means only that the horizon has elapsed, not that outcome prices have been verified.

## Capture new independent selection events

```sh
uv run python -m app.analysis.forward_journal_cli capture \
  --dir ~/StockTradingWebResearch \
  --horizon 20
```

- On an already registered signal/rule/horizon, prints `SKIPPED` before any full-market historical scan. A small exchange-calendar request may still occur.
- On a valid new signal, runs the current `forward_cli` full-market Alpaca scan, stores the new checkpoint under `~/StockTradingWebResearch/checkpoints/`, and creates a SHA-256 pin under `~/StockTradingWebResearch/journal/`.
- If the entry trading date has begun in New York, conservatively skips instead of pretending the prior day's trade could be entered at the already-passed open. **Run after the prior completed session and on a New York calendar date *before* the next trading session**. The existing implementation's safe SIP cutoff usually makes this the following calendar day, before the next exchange date.
- A failed/incomplete scan does not create a journal pin. A partially written or unregistered checkpoint is preserved and must be inspected manually; it is never silently deleted or overwritten.
- On macOS/Linux, registration and scans under one research directory are serialized by an advisory file lock. This is not a remote distributed lock.

**No automatic schedule is installed.** Run this manually while testing. A later patch can add optional scheduling after determining a reliable daily run window and how to handle a sleeping/offline Mac and provider limits. Missing days are missing observations, never reconstructed from hindsight.

## How the local research evidence is protected

Each journal pin is a new, non-overwritable JSON file containing the source path, its **independently supplied original checksum**, signal session, horizon, and scanner rule. Every journal read verifies both the pin and its referenced checkpoint. If any registered source is missing, tampered with, or moved, `status` blocks rather than quietly dropping it.

The original checkpoint is unchanged. A journal pin is also a *local* record, not a trusted external timestamp or independently notarized evidence; back up checkpoints and their printed hashes outside the machine. Do not commit research data, API credentials, or `.env` to Git. The series records separate **selection events**, whose future holding periods may overlap. They are not automatically independent trials.

No database migration and no trades. This version does **not** create outcome audits or a cumulative return series. The existing `evaluate_forward_cli` remains the tool for each checkpoint after its horizon matures; aggregation across multiple audit files should be implemented separately with conservative missing-data/cost handling.
