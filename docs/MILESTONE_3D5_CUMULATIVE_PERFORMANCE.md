# Milestone 3D.5 — Read-only cumulative forward research reporting

## Purpose

Summarize **all** registered prospective checkpoints in the local forward journal, rather than spotlighting successful picks. This is a *descriptive research report*, **not** a validated investment strategy or a portfolio trading record.

The existing `forward_outcomes_cli` continues to own evaluation and research audit creation. This new CLI **never fetches historical outcome bars, writes research files, places orders, or alters the macOS scheduler**. It may request the Alpaca exchange calendar through the existing journal status interface to determine maturity.

## Usage

From `backend` after the patch and tests:

```bash
uv run python -m app.analysis.forward_performance_cli --dir ~/StockTradingWebResearch
```

For machine-readable output to stdout:

```bash
uv run python -m app.analysis.forward_performance_cli --dir ~/StockTradingWebResearch --json
```

The JSON contains a schema version, generation UTC timestamp, complete status counts, one group per `(frozen research rule, holding sessions)`, descriptive metrics when and only when there are complete observations, explicit date-window overlap diagnostics, and source checkpoint / outcome SHA-256 digests for every complete observation.

**Expected initial behavior:** The registered November 13, 2026 signal should remain `PENDING`, with **no** return statistics, until its forward evaluation has matured and been completed. Do not run `evaluate-ready` to force a premature outcome.

## Denominators and integrity

- `registered_checkpoints` counts every pinned checkpoint; `PENDING`, `READY`, `COMPLETE`, `INCOMPLETE`, and `NO_SELECTION` all remain visible.
- `COMPLETE` only contributes return statistics if all frozen selections **and SPY** have usable entry and exit data and the original audit passes integrity and source-identity verification.
- Recalculate each complete stock's **gross and net** open-to-open percentage return from its saved split-adjusted prices and the frozen **10-basis-point per side** friction assumption. Cross-check the saved mean, benchmark, excess, winner count and beat-benchmark indicator. A mismatch blocks the entire report, never silently omits the observation.
- Different scanner rule identifiers and different holding horizons are not pooled. This avoids counting strategy changes as a single uninterrupted track record.
- A small compatibility correction in `forward_outcomes.py` allows the expected *one 0.0001 percentage-point unit* discrepancy between independently rounded equal-weight average and excess values. This is checked more strictly against the recorded stock prices by the new reporter.

## Meaning of metrics

All percentages refer to **one full holding-period return per completed checkpoint**, after the same assumed cost. The selected return is an equal-weight arithmetic mean over frozen constituents *within that checkpoint*. The SPY return covers the **same entry and exit session** with the same assumed cost. `paired_excess_pp` is their difference in **percentage points**.

For each rule/horizon group, report the unweighted arithmetic mean and median of the paired per-checkpoint returns, best/worst paired excess, the **descriptive population standard deviation** of paired excess values, counts of positive-selection windows, counts that outperform SPY, and window overlap diagnostics. These values **are not** compounded wealth, equity growth, CAGR, risk-adjusted returns, statistical confidence intervals, a Sharpe ratio, a profit probability, or financial advice.

Open-to-open exposure windows overlap when one entry precedes the other's exit and vice versa. Overlap diagnostics report pair counts, affected observations, peak simultaneous windows, and the maximum number of chronologically nonoverlapping windows (not an inferred effective statistical sample size). Adjacent windows meeting exactly at an exit/entry open are not considered overlapping.

## Current limitations

- Adjacent trading days with 20-session holding periods are highly overlapping. Treat them as correlated observations; no independence is assumed.
- Missing, delisted, no-selection, and invalid-price results can cause **completion bias**. The report preserves counts but does not create substitute returns.
- Averages across overlapping windows **do not describe an implementable capital-constrained strategy**, and the best/worst outcome is not drawdown. Portfolio capital allocation, rebalancing, cash drag, dividends, merger consideration, delisting proceeds, genuine execution spreads/slippage, taxes, and market impact require separate work.
- Current Alpaca asset-directory names and security types are not authoritative. Checkpoint creation time and hash are local, not independently certified.
- The CLI uses the existing journal's maturity status; if calendar verification fails or any source checksum disagrees, it stops instead of reporting a partial success.
- One or even many correlated complete evaluations do not prove predictive skill. Avoid tuning the scanner on this same forward evaluation set.
