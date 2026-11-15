# Milestone 3F — Complete prospective prediction and validation (one patch)

**One release, no 3F.1/3F.2/3F.3.** This milestone encompasses the prediction pipeline, training, time-safe validation, strict publication gates, candidate ranking, budget allocation integration, scheduled maturation, user interface, tests, and read-only diagnostics. The system is **not** authorized to place trades.

## The central scientific limitation

A model that predicts returns from historical adjusted price bars can appear excellent even when it has simply exploited hindsight, corporate actions, survivorship selection, or look-ahead. This application has recorded only a small number of genuinely prospective full-market scans so far. **It cannot honestly claim current predictive skill.** The correct 3F initial state is **`insufficient_evidence`**; numeric probabilities and predictive allocations are withheld until enough completed future outcomes accumulate and predeclared gates are met.

This is a functioning prediction *research system*, not a finished profitable investment strategy. A failed gate is a substantive research result, not a defect to hide or a reason to weaken the criteria after seeing test returns.

## Data and model — complete in this patch

1. Each independent, dated 20-session scanner checkpoint from the existing research journal remains frozen. Its original checksum, scanner rule, signal date, rank, source metrics, and candidate symbols are verified; all future returns are excluded from the input feature vector.
2. Only `COMPLETE` outcomes from the existing forward-outcome journal are eligible. Those audits are independently rechecked against split-adjusted entry and exit opening prices; the strategy cost assumption is **10 basis points on each side** for stock and SPY. `PENDING`, `READY`, `INCOMPLETE`, and `NO_SELECTION` remain counted but do not become training targets. A corrupt `COMPLETE` record blocks publication.
3. The model predicts the *conditional probability* that a scanner-selected stock's net return **beats SPY** over **20 subsequent exchange sessions**. This is **not** the probability that the stock price rises, the probability that investing makes money, or an estimate of expected dollars earned.
4. Predeclared fixed input features are captured 20/60-session return, annualized volatility, 60-session drawdown, approximate historical dollar volume, and the scanner score. A small, deterministic, L2-regularized logistic regression runs in pure Python. Fixed scaling, 250 optimizer iterations, coefficient regularization, no hyperparameter search or random shuffle, and the fixed target are part of the frozen 3F methodology. No paid feeds or ML dependencies are required.
5. **Expanding walk-forward validation** trains only on labels whose outcome **exit is strictly before** each test **signal**. For bounded web latency, the test-signal schedule is fixed in advance to every fifth calendar-ordinal day; this schedule is independent of outcomes. It compares per-stock Brier scores with a prior probability derived only from the training cohort, and compares the two highest model-ranked candidates against SPY and the scanner's original top two. Overlapping test windows are not called independent results.
6. **All validation gates must pass** before the model may rank a shortlist for optional experimental allocations: at least 20 walk-forward windows, at least 200 tested stocks, at least eight date-disjoint holding windows, an absolute Brier improvement of at least 0.002 against the expanding prior, a positive mean top-two excess against SPY, and a nonnegative mean improvement over the original scanner ranking. This is a basic research gate, not a proof of statistical significance. Each training fit additionally needs 30 completed distinct earlier signal windows, at least 200 previous stock observations, and both outcome classes (at least 20 each). The gate is recomputed using **only information available before the proposed signal**.
7. Candidate publication also requires an estimated model probability >= 0.55 and at least 0.03 greater than the *historical training* prior. Only already-quality-screened candidates enter the model's candidate ranking. The existing SEC CIK, SIC concentration, historical co-movement, 10% individual-stock limit, affordable-loss limit, and cash-preservation logic remain mandatory when their respective options are enabled.
8. Model evidence is computed read-only from immutable journal sources. No train-now endpoint can edit or relabel historical outcomes; no model artifacts or synthetic results are written. Reports carry a SHA-256 digest of the exact reference checkpoint and audit hashes (local fingerprints, **not** independently certified timestamps).

## Existing macOS scheduled research — integrated

The user's **already installed** `com.stocktradingweb.forward-research` LaunchAgent continues to invoke `app.analysis.forward_schedule_cli run-once` during the 08:00–08:59 New York window. **This patch extends that same command:** after the scanner capture attempt finishes, the scheduler checks for mature, missing outcomes and processes up to **five** using the existing verified evaluator. These mature audits may make **additional historical Alpaca calls**; they do not call brokerage order endpoints. Their immutable source journal pins are never overwritten. Evaluations do not occur outside the New York morning window. Failure is reported, not silently treated as success. Nothing retroactively creates missing scans for sleeping/offline days; an awake Mac, internet connection and correctly configured free Alpaca credentials are required.

Manual operations remain available:

```bash
cd ~/StockTradingWeb/backend
uv run python -m app.analysis.forward_outcomes_cli status --dir ~/StockTradingWebResearch
uv run python -m app.analysis.forward_outcomes_cli evaluate-ready --dir ~/StockTradingWebResearch --limit 5
uv run python -m app.analysis.prediction_cli report --dir ~/StockTradingWebResearch
```

The last command is a **read-only** JSON report and never asks the market-data provider for future prices. The outcome evaluation command does request only matured historical price observations.

## Website integration

- `/forecasts` is now an actual **Forecast Lab**, replacing the placeholder. It displays model status, completed prospective sample size, walk-forward counts, Brier score and expanding-prior baseline, top-two excess-vs-SPY and original-scan comparisons, individual predeclared gate results, source fingerprint, and limitations. The UI does **not** invent performance numbers when there are none.
- `GET /api/research/prediction-validation` provides the same audited report. Corrupt/unavailable records produce 503; error details do not disclose user file paths.
- `/planner` adds an **optional** `Require prospective prediction evidence` switch. Default planner behavior and no-experimental-stock requests remain unchanged. When enabled and research gates pass, the model may rank **up to 20 eligible shortlisted candidates**, of which at most two can receive illustrative experimental slices. All other budget, quality, identity, industry, correlation and loss-cap controls still apply.
- If there are not enough dated, matured outcomes, validation fails, fresh scanner features are missing, a candidate falls below the probability thresholds, or source evidence is unavailable, its proposed dollars stay cash. No fallback to a guessed prediction or a popular ticker is allowed.

## Checks on the actual cloned repository

**Backend suite**:

```bash
cd ~/StockTradingWeb/backend
uv run pytest -q
uv run ruff check .
uv run mypy app
uv run alembic check
```

**Frontend suite**:

```bash
cd ~/StockTradingWeb/frontend
pnpm exec vitest run
pnpm lint
pnpm build
```

Then open `/forecasts` and `/planner` with and without the optional model switch. You should expect `insufficient_evidence` initially, with experimental stock dollars kept as cash if prediction evidence is required. Verify no provider data is requested just to load the Forecast Lab; **mature-audit evaluation** and optional co-movement independently use existing historical providers.

## Scope limitations — intentionally not papered over

- The training cohort contains **scanner-selected securities only**, not a representative full-universe panel. The model is conditional on the historical scanner selection process and cannot tell you which of every US-listed stock will rise most.
- SEC identity cross-reference and SIC tags are independent metadata safeguards, not proof that instruments are ordinary common stock, and SIC is not a full sector-level exposure analysis.
- **No multi-decade, point-in-time reconstructed backtest** is fabricated; source features are the values actually frozen at each recorded scan. A valid prospective evaluation takes calendar time.
- The Brier and top-two evidence thresholds are predeclared guardrails, **not formal statistical proof**, independent-sample confidence intervals, estimated CAGR, or an investment recommendation.
- Commission, spread, slippage, corporate-action, tax, market-impact and delisting effects are not fully simulated by the existing 10-bps-each-side outcome protocol.
- The benchmark SPY, cash percentage, time-horizon policy, maximum-loss stress checks and 10% position cap remain **illustrative**. 3F does not optimize expected return or claim a trustworthy optimal portfolio. The model can improve how the scanner candidates are ranked *if* evidence supports it.
- Model status can legitimately remain below the research gate indefinitely. No paid service, trading API, account access, or broker orders are added.
