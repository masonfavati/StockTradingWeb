StockTradingWeb 3J — Beginner-Friendly Stock History and Explanations
===================================================================
Apply on merged 3I main in a new feature branch:
  unzip -o ~/Downloads/StockTradingWeb_3J_Beginner_History_Insights.zip -d ~/StockTradingWeb

COMPLETE ONE-PATCH FEATURE
- On-demand historical prices still come from the existing Alpaca chart endpoint,
  independently of Find Opportunities scans. No additional provider queries are
  required for the new descriptive summaries.
- Historical chart now explains highest/lowest adjusted prices, biggest observed
  fall from a prior high, average magnitude of changes between observed dates,
  counts of higher/lower/unchanged intervals, and SPY performance difference on
  matching real dates only. High/low markers appear on the existing SVG chart.
- New beginner guide at /start, shared definitions and plain-language copy across
  navigation, Home/research, Find Opportunities, Decision Desk, chart, budget
  planner, budget comparison, watchlist, and prediction lab.
- Raw training methods, numerical screening thresholds, and source details can
  be expanded when desired; important limits remain prominent.
- Tests cover calculated summaries, edge cases, beginner definitions, basic
  navigation and accessible chart explanations.

BEHAVIORAL GUARANTEES
- No trades, database changes, new paid services, model retraining, fake prices,
  future-price curve, or forward-looking promise.
- Daily history remains bounded and cached, with the existing closed-session
  cutoff and the existing provider restrictions.
- Historical adjusted prices reflect corporate actions known today and are not
  time-stamped prediction inputs or live executable prices.
- Correlation, identity, industry, prediction, and budget risk rules are unchanged.
- SPY comparison is historical and date-aligned, not an estimate of profits.

LOCAL VERIFICATION (TWO SUITES)
Backend:
  cd ~/StockTradingWeb/backend
  uv run pytest -q
  uv run ruff check .
  uv run mypy app
  uv run alembic check
Frontend:
  cd ~/StockTradingWeb/frontend
  pnpm exec vitest run
  pnpm lint
  pnpm build

WEBSITE CHECKS
1) /start is readable without prior investing experience, and its links work.
2) /history?symbol=AAPL loads without a scan; 1-month/1-year/5-year work.
3) Historical high/low and biggest observed drop match dates shown in the chart.
4) SPY comparison uses only dates shared by both stocks, never made-up prices.
5) No future-price line appears; its limitation is easy to understand.
6) /scanner, /decisions, /planner, /compare, /forecasts, and watchlist all have
   simple introductory text and accessible definitions.
7) /planner still respects the same risk limit, SEC identity and industry,
   co-movement, and validation gates; rejected stock dollars remain cash.

Local reconstruction is incomplete (it lacks unrelated original app modules and
frontend packages). Complete repository checks must run on the user's Mac.
