# Milestone 3H — Budget Comparison Workspace

## Scope: one complete feature, one PR

New `/compare` page links the existing Research Decision Desk and Investment Planner.
It compares **Cautious / Balanced / Growth-oriented** illustrative allocations
under the same user-entered budget, holding horizon, affordable-loss cap, and
(optional) existing experimental-stock evidence rules. It is not an optimizer,
return forecast, price quote, portfolio, execution order, or best-style ranking.

### Capabilities

- Side-by-side **invested/core ETF / experimental stock ideas / retained cash**
  amounts, individual allocation lines with reasons, and the existing 30%-equity
  stress scenario, with an explicit warning that it is not a loss guarantee.
- Optional experimental candidates with controls for the existing **SEC filer**,
  **SEC SIC**, **prospective prediction**, and **historical co-movement** gates.
  Evidence is enabled by default when users opt in to experimental stocks.
- An explicit user click starts **three read-only `/api/research/budget-plan`**
  requests. No automatic scan, portfolio transaction, database migration, or
  new credentials/service is needed. If experimental ideas pass other gates and
  historical co-movement is enabled, each scenario can make an existing bounded
  history request; this is disclosed in the UI.
- Validates the amount in **integer cents** (0.01–1,000,000.00), optional loss cap
  and all returned allocations. Rejects incomplete/mismatched plans, incorrect
  money totals, or an inconsistent 30% stress scenario beyond a one-cent
  independently rounded display tolerance. On a request failure,
  the UI publishes **no partial comparison**.
- When experimental candidates are enabled, refuses to compare plans from
  different research source kinds, signal sessions, eligible-source states, or
  conflicting nonempty SEC/industry/prediction source hashes. The three API
  requests are not an atomic snapshot; this protects against an obviously
  inconsistent comparison but does not promise atomicity.
- Exports a local **CSV** of the received allocation lines and evidence statuses,
  with spreadsheet-formula injection protection. The file does **not** certify
  the data or represent an executable trade.
- Links to `/planner` pre-filling selected assumptions and evidence toggles,
  without starting a request. Malformed/unreasonable query parameters are
  ignored, and the existing planner's normal server-side validation still runs
  on submission.

### Existing safety limits unchanged

- The server remains authoritative; the comparison does not invent or override
  the core/experimental risk weights, loss limits, candidate selection, or
  prospective-model approval gate.
- Future performance cannot be inferred from past screening. As of initial
  deployment, **insufficient validated future outcomes** are likely to mean
  experimental prediction-dependent dollars remain cash.
- Disabling a gate does not constitute verified eligibility. The full planner
  shows the complete per-candidate evidence; the comparison is a summary.
- Historical co-movement analysis can create up to three bounded provider
  history requests when experimental stock allocations are available.

### Manual acceptance checks

1. `/compare` opens from the main navigation, dashboard, planner, and Decision
   Desk; loading the page itself triggers **no budget or market request**.
2. Enter `$100`, `5+ years`, leave experimental OFF, click **Compare three
   allocation styles**: absent a binding loss cap, Cautious `60/40`, Balanced
   `65/35`, and Growth-oriented `70/30` invested/cash, each totaling `$100`.
   This is illustrative preset behavior, not a recommendation.
3. Change to `1–5 years`, enter a maximum affordable loss, compare again. Check
   invested/cash sums and the loss stress row for every style.
4. Enable experimental ideas; by default all four available evidence gates are
   on. Before model validation passes, experimental allocations should stay
   cash (if that evidence requirement is enabled).
5. Open a style in the full planner: selected budget, style, horizon, cap and
   gate settings are prefilled **without submitting any new calculation**.
6. Export CSV and verify scenario names, allocation rows, dollar sums, source
   session, and evidence statuses; no broker order is involved.
7. Enter malformed input (`100.001`) or affordable loss greater than budget:
   validation appears immediately and **no requests** are sent.
8. If one of the three requests fails or research evidence changes in flight,
   the page does **not** display partial results.

### Quality suites (Mac)

**Backend** (unchanged by this patch):

```bash
cd ~/StockTradingWeb/backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

**Frontend**:

```bash
cd ~/StockTradingWeb/frontend
pnpm exec vitest run
pnpm lint
pnpm build
```

Includes unit tests for integer-cent arithmetic, exact accounting, source
consistency, CSV escaping, prefill validation and request behavior, plus UI tests
for the comparison page and one prefill regression in the existing planner.
