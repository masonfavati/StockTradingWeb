# Milestone 3D.4: Bounded forward-outcome journal

This patch adds an **additive, manual first-pass outcome sweeper** to the journal.
It does not modify the morning LaunchAgent or original checkpoint files.

## Commands

From `backend`:

```bash
uv run python -m app.analysis.forward_outcomes_cli status --dir ~/StockTradingWebResearch
```

This verifies every journal pin and reports PENDING, READY, COMPLETE,
INCOMPLETE, or NO_SELECTION. It obtains the verified Alpaca exchange calendar,
but it **does not fetch historical prices**. A READY checkpoint has matured
according to the exchange calendar but has no outcome audit yet.

When a checkpoint reaches READY, explicitly invoke:

```bash
uv run python -m app.analysis.forward_outcomes_cli evaluate-ready \
  --dir ~/StockTradingWebResearch --limit 1
```

The batch is bounded: default one, maximum 20 checkpoints. It delegates each
mature checkpoint to the **existing** `evaluate_forward_cli` with the pinned
source file and checksum, one fixed predeclared cost of 10 basis points per
side, and SPY benchmark. Each outcome is written as a new, non-overwritable
JSON at `~/StockTradingWebResearch/outcomes/<journal-pin-name>.json`.

Existing outcome files are verified and never retried or overwritten. If
an evaluation fails, it is reported; the record remains READY if no file
was produced. If a partial/invalid file exists, the next run blocks until it
is manually inspected, never silently replaces it.

INCOMPLETE means at least one opening price or benchmark observation could not
be evaluated; **no complete-portfolio performance claim** is made. No missing
prices or securities are replaced. COMPLETE produces only the predeclared
chosen portfolio/benchmark comparison and is one research observation.

## Boundaries

- No live orders or trading automation.
- No independent cryptographic timestamping or external attestation.
- The reported SHA-256 detects changes but does not prove when a record existed.
- Split-only price adjustment is not a total-return or executable-order model.
- ETF/warrant/units and thin liquidity remain limitations in the frozen universe.
- Inference requires multiple independent dates, an unbiased universe, and
  predeclared statistical methods; a small number of outcomes is not proof.
- Only a **manual** outcome batch is supported by this patch. Enabling an
  automatic outcome scheduler is a separate, opt-in milestone.
