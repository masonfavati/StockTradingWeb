import { useEffect, useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { AllocationWheel, GrowthBar, HistoryWithEstimatedEndpoint } from './VisualInsights'
import { currency } from './money'
import {
  getGrowthPlan, getScannerProgress, startMarketScan,
  type GrowthPlanResponse, type HoldingPeriod, type PlanStyle,
} from './investingApi'

function validAmount(value: string, optional = false) {
  if (optional && !value.trim()) return true
  return /^\d+(?:\.\d{1,2})?$/.test(value) && Number(value) >= (optional ? 0 : 0.01) && Number(value) <= 1_000_000
}

export default function InvestingHomePage() {
  const [budget, setBudget] = useState('100')
  const [style, setStyle] = useState<PlanStyle>('balanced')
  const [horizon, setHorizon] = useState<HoldingPeriod>('long')
  const [maxLoss, setMaxLoss] = useState('')
  const [symbols, setSymbols] = useState('')
  const [exploratory, setExploratory] = useState(false)
  const [busy, setBusy] = useState(false)
  const [status, setStatus] = useState('')
  const [error, setError] = useState('')
  const [plan, setPlan] = useState<GrowthPlanResponse | null>(null)
  const [chosen, setChosen] = useState('')
  const stopped = useRef(false)
  // React StrictMode runs an effect setup -> cleanup -> setup cycle in
  // development. Re-arm the flag on *every* setup; cleanup-only logic leaves
  // it permanently true, skipping all scanner polling and the loading reset.
  useEffect(() => {
    stopped.current = false
    return () => { stopped.current = true }
  }, [])
  function invalidate() {setPlan(null); setError(''); setStatus('')}

  async function makePlan(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    invalidate()
    if (!validAmount(budget) || !validAmount(maxLoss, true) || (maxLoss && Number(maxLoss) > Number(budget))) {
      setError('Enter a valid budget and a loss limit no larger than your budget.')
      return
    }
    const chosenSymbols = symbols.toUpperCase().split(/[\s,]+/).filter(Boolean)
    if (chosenSymbols.length > 10 || chosenSymbols.some(s => !/^[A-Z][A-Z0-9.-]{0,19}$/.test(s))) {
      setError('Enter up to ten valid stock symbols, separated by commas.')
      return
    }
    setBusy(true)
    try {
      const input = {
        budget_usd: Number(budget).toFixed(2), style, horizon,
        max_loss_usd: maxLoss ? Number(maxLoss).toFixed(2) : null,
        allow_exploratory: exploratory, symbols: chosenSymbols,
      }
      let result: GrowthPlanResponse
      try {
        result = await getGrowthPlan(input)
      } catch (cause) {
        if (!(cause instanceof Error && 'status' in cause && cause.status === 409 && !chosenSymbols.length)) throw cause
        // Only start the expensive whole-market search after the user's button
        // click. Never scan on page load and never pass off a partial scan as final.
        setStatus('No recent market-wide shortlist. Searching the market now; this can take several minutes.')
        await startMarketScan()
        let complete = false
        for (let attempt = 0; attempt < 300 && !stopped.current; attempt++) {
          // Check once immediately after the 202 response, then every two
          // seconds. A completed scan should not leave the button spinning.
          if (attempt > 0) await new Promise<void>(resolve => setTimeout(resolve, 2000))
          if (stopped.current) break
          const progress = await getScannerProgress()
          if (stopped.current) break
          setStatus(progress.message)
          if (progress.state === 'failed') throw new Error('The market search failed. Your plan was not estimated.')
          if (progress.state === 'idle') throw new Error('The market search was interrupted. Please try again.')
          if (progress.state === 'complete') { complete = true; break }
        }
        if (!complete) throw new Error('The market search has not finished. Try again after it completes.')
        result = await getGrowthPlan(input)
      }
      if (!stopped.current) {
        setPlan(result)
        setChosen(result.ranked_stocks[0]?.symbol ?? '')
        setStatus('')
      }
    } catch (cause) {
      if (!stopped.current) {
        setError(cause instanceof Error ? cause.message : 'The plan could not be created.')
        setStatus('')
      }
    } finally {if (!stopped.current) setBusy(false)}
  }

  const chosenIdea = plan?.ranked_stocks.find(item => item.symbol === chosen)
  const stockPositions = plan?.plan.allocation.filter(row => row.category === 'experimental_stock') ?? []
  const includedStockSymbols = new Set(stockPositions.map(row => row.symbol))
  function allocationNote(symbol: string, estimate: number): string {
    if (estimate <= 0) return 'Excluded from money split: estimated change is not positive.'
    if (!plan) return ''
    if (includedStockSymbols.has(symbol)) return 'Included in experimental money split.'
    if (!plan.plan.exploratory) return 'Research only: individual stocks are not allocated in this scenario.'
    if (plan.selection.source === 'user_selected_tickers_not_entire_market') {
      return 'Research only: user-entered stocks have not passed the market-wide quality screen.'
    }
    const reason = plan.plan.declined.find(row => row.symbol === symbol)
    return reason ? `Not allocated: ${reason.reason}.` : 'Not allocated after portfolio risk and diversification checks.'
  }
  const preview = chosen ? (plan?.preview_history[chosen] ?? []) : []
  return <section className="space-y-6" aria-label="Growth and investment planning">
    <header className="rounded-3xl border border-emerald-700/50 bg-gradient-to-r from-emerald-950 to-slate-900 p-6 sm:p-9">
      <p className="text-xs font-semibold uppercase tracking-widest text-emerald-300">Your money, your plan</p>
      <h1 className="mt-2 text-3xl font-bold sm:text-4xl">How could I spread out my investment?</h1>
      <p className="mt-3 max-w-2xl text-sm text-slate-300">Start with an amount. See a visual money split and experimental growth estimates based on years of historical prices—not just previous searches.</p>
      <div className="mt-5 flex flex-wrap gap-3 text-sm">
        <Link to="/portfolio" className="rounded-lg border border-emerald-600 px-4 py-2 text-emerald-200 hover:bg-emerald-900">See the stocks I actually own</Link>
        <Link to="/start" className="rounded-lg border border-slate-700 px-4 py-2 text-slate-300 hover:bg-slate-800">New to stocks? Start here</Link>
      </div>
    </header>

    <form onSubmit={makePlan} className="space-y-5 rounded-2xl border border-slate-700 bg-slate-900 p-5 sm:p-7">
      <div className="grid gap-4 md:grid-cols-3">
        <label className="text-sm font-semibold">My budget ($)
          <input aria-label="Investment budget" inputMode="decimal" value={budget}
            onChange={e => {setBudget(e.target.value); invalidate()}}
            className="mt-2 block w-full rounded-lg border border-slate-600 bg-slate-950 p-3 text-xl" />
        </label>
        <label className="text-sm font-semibold">When might I need it?
          <select value={horizon} aria-label="Investment time frame" onChange={e => {setHorizon(e.target.value as HoldingPeriod); invalidate()}}
            className="mt-2 block w-full rounded-lg border border-slate-600 bg-slate-950 p-3">
            <option value="short">Within 1 year</option><option value="medium">1–5 years</option><option value="long">5+ years</option>
          </select>
        </label>
        <label className="text-sm font-semibold">How much could I afford to lose? ($)
          <input aria-label="Maximum affordable loss" inputMode="decimal" value={maxLoss}
            onChange={e => {setMaxLoss(e.target.value); invalidate()}} placeholder="Optional"
            className="mt-2 block w-full rounded-lg border border-slate-600 bg-slate-950 p-3" />
        </label>
      </div>
      <fieldset className="space-y-2">
        <legend className="text-sm font-semibold">Investment approach</legend>
        <div className="flex flex-wrap gap-2">
          {(['cautious', 'balanced', 'growth'] as const).map(choice => <button key={choice} type="button"
            aria-pressed={style === choice} onClick={() => {setStyle(choice); invalidate()}}
            className={`rounded-full border px-4 py-2 capitalize ${style === choice ? 'border-emerald-400 bg-emerald-900 text-white' : 'border-slate-700 text-slate-300'}`}>{choice}</button>)}
        </div>
      </fieldset>
      <label className="flex items-start gap-3 rounded-xl border border-amber-800/60 bg-amber-950/20 p-4 text-sm">
        <input type="checkbox" checked={exploratory} onChange={e => {setExploratory(e.target.checked); invalidate()}} className="mt-1" />
        <span><strong>Show an experimental plan with individual stocks</strong><span className="mt-1 block text-slate-300">The model is still unproven. Individual stock slices are capped and are for exploring—not instructions to purchase.</span></span>
      </label>
      <details className="rounded-xl border border-slate-800 p-4 text-sm">
        <summary className="cursor-pointer text-slate-300">Optional: compare particular stocks instead of the market shortlist</summary>
        <label className="mt-3 block">Stock symbols, separated by commas
          <input aria-label="Optional stock symbols" value={symbols} onChange={e => {setSymbols(e.target.value); invalidate()}}
            placeholder="e.g. AAPL, MSFT, NVDA" className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 p-3" />
        </label>
        <p className="mt-2 text-xs text-slate-400">Using your own list does not search the entire market. Otherwise the app uses the latest completed broad-market shortlist or starts a new search after you click.</p>
      </details>
      <button disabled={busy} type="submit" className="w-full rounded-xl bg-emerald-600 p-4 text-lg font-bold text-white disabled:opacity-60">
        {busy ? 'Studying the market…' : 'Build my investment picture'}
      </button>
      {status && <p role="status" className="text-sm text-cyan-200">{status}</p>}
      {error && <p role="alert" className="rounded-xl border border-red-800 bg-red-950/30 p-3 text-sm text-red-200">{error}</p>}
    </form>

    {plan && <div className="space-y-6">
      <div className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <p className="text-sm font-semibold text-emerald-300">Your illustrated money split</p>
        <h2 className="mt-1 text-2xl font-bold">{currency(plan.plan.budget_usd)} budget</h2>
        <div className="mt-5"><AllocationWheel allocations={plan.plan.allocation} /></div>
        {stockPositions.length > 0 && <div className="mt-5 rounded-xl border border-emerald-800/50 bg-slate-950 p-4">
          <h3 className="font-semibold text-emerald-300">Illustrative contributions to individual stocks</h3>
          <p className="mt-1 text-sm text-slate-300">These dollar amounts come from comparing feasible combinations of positive-estimate stocks, adjusting for historical downside, uncertainty, and overlapping price movements. No purchases are placed.</p>
          <ul className="mt-3 space-y-2">{stockPositions.map(row => <li key={row.symbol} className="flex flex-wrap items-center justify-between gap-2 border-t border-slate-800 pt-2 text-sm">
            <span><strong>{row.symbol}</strong> <span className="text-slate-400">· {row.percent_of_budget}% of your budget</span></span>
            <strong className="tabular-nums">{currency(row.amount_usd)}</strong>
          </li>)}</ul>
        </div>}
        {plan.plan.combination_analysis && <p className="mt-4 text-xs text-slate-300" role="note">
          {plan.plan.combination_analysis.risk_eligible_stocks} of {plan.plan.combination_analysis.forecasted_stocks_reviewed} forecasted stocks passed the positive-estimate and risk screens.
          {' '}{plan.plan.combination_analysis.combinations_considered} combinations were evaluated; {plan.plan.combination_analysis.stock_positions_selected} stocks were selected.
          {' '}Illustrative model change in the shown investments over the {plan.plan.forecast_period} forecast period: {currency(plan.plan.combination_analysis.illustrative_model_gain_usd)} (not a reliable profit prediction).
        </p>}
        <div className="mt-5 grid grid-cols-2 gap-3 text-center">
          <div className="rounded-xl bg-slate-950 p-4"><p className="text-xs text-slate-400">Shown as invested</p><p className="text-xl font-bold">{currency(plan.plan.invested_usd)}</p></div>
          <div className="rounded-xl bg-slate-950 p-4"><p className="text-xs text-slate-400">Money kept as cash</p><p className="text-xl font-bold">{currency(plan.plan.cash_usd)}</p></div>
        </div>
        {plan.selection.note ? <p role="status" className="mt-4 rounded-lg border border-amber-800 bg-amber-950/20 p-3 text-sm text-amber-200">{plan.selection.note}</p> :
          <p className="mt-4 text-xs text-amber-200">{plan.plan.exploratory ? 'Experimental allocation illustration only; the prediction model is not prospectively validated.' : 'No experimental individual stocks were allocated. Toggle the research scenario above to explore—but not validate—individual-stock positions.'}</p>}
        {plan.plan.declined.filter(row => row.symbol === 'SPY').map(row => <p key="spy-exclusion" className="mt-2 text-sm text-amber-200">SPY not allocated: {row.reason}. That amount remains cash.</p>)}
        {plan.plan.exploratory && plan.ranked_stocks.length > 0 && !plan.plan.allocation.some(row => row.category === 'experimental_stock') &&
          <p className="mt-2 text-sm text-slate-300">No individual stock passed the complete allocation decision. Stocks with negative estimates or excessive modeled downside, uncertainty or concentration remain excluded; their money stays as cash.</p>}
      </div>

      {plan.scenario_comparison && <section aria-label="Compare investment approaches" className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <h2 className="text-2xl font-bold">Compare three ways to use this budget</h2>
        <p className="mt-2 text-sm text-slate-300">All three approaches use the same budget, forecast horizon, and affordable-loss limit. The third searches every eligible combination of up to four stocks among the bounded screened forecasts, with or without SPY, and shows the single highest experimental model-dollar outcome. It does not predict which portfolio will actually earn the most.</p>
        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          {plan.scenario_comparison.approaches.map(approach => <article key={approach.id}
            className={`rounded-xl border p-4 ${approach.id === 'max_model_change' ? 'border-cyan-700 bg-slate-950' : approach.id === 'combined' ? 'border-emerald-700 bg-slate-950' : 'border-slate-700 bg-slate-950/50'}`}>
            <h3 className="font-semibold">{approach.label}</h3>
            {approach.id === 'combined' && <p className="mt-1 text-xs text-emerald-300">Your main money split above</p>}
            {approach.id === 'max_model_change' && approach.available && <p className="mt-1 text-xs text-cyan-300">Highest among the eligible combinations tested · not a verified future winner</p>}
            {!approach.available && <p className="mt-2 text-xs font-semibold text-amber-300">Maximum-change comparison unavailable</p>}
            <p className="mt-3 text-sm text-slate-300">Shown as invested: <strong>{currency(approach.invested_usd)}</strong></p>
            <p className="mt-1 text-sm text-slate-300">Kept as cash: <strong>{currency(approach.cash_usd)}</strong></p>
            {approach.available && <>
              <p className="mt-3 text-sm text-cyan-200">Experimental {plan.scenario_comparison?.forecast_period} model dollar change: <strong>{approach.illustrative_model_gain_usd !== null ? `${Number(approach.illustrative_model_gain_usd) > 0 ? '+' : ''}${currency(approach.illustrative_model_gain_usd)}` : 'Unavailable'}</strong></p>
              {approach.past_window_range ? <p className="mt-2 text-xs text-slate-300">Worst observed same-length historical window: <strong>{approach.past_window_range.worst_observed_change_pct}%</strong> of total budget ({approach.past_window_range.windows_compared} disjoint past windows). Not a maximum possible loss.</p> :
                <p className="mt-2 text-xs text-slate-400">No comparable historical downside-window result.</p>}
            </>}
            <ul className="mt-3 space-y-1 border-t border-slate-800 pt-3 text-xs text-slate-300">
              {approach.allocation.filter(row => Number(row.amount_usd) > 0).map(row =>
                <li className="flex justify-between gap-2" key={`${approach.id}-${row.symbol ?? 'cash'}`}>
                  <span>{row.symbol ?? 'Cash'}</span><strong>{currency(row.amount_usd)}</strong>
                </li>)}
            </ul>
            <p className="mt-3 text-xs text-slate-400">{approach.explanation}</p>
          </article>)}
        </div>
        <p className="mt-4 text-xs text-amber-200" role="note">{plan.scenario_comparison.method_warning}</p>
      </section>}

      <div className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex flex-wrap items-baseline justify-between gap-3"><h2 className="text-2xl font-bold">{plan.selection.note ? 'Individual-stock research status' : 'Stocks ranked by estimated growth'}</h2>
          <span className="rounded-full border border-amber-700 px-3 py-1 text-xs text-amber-200">Experimental predictions</span></div>
        <p className="mt-2 text-sm text-slate-400">{plan.selection.note ? 'There are no verified individual-stock ideas to rank from this completed scan.' : plan.selection.source === 'user_selected_tickers_not_entire_market' ? 'Only stocks you entered are compared.' : 'Only a bounded quality-screened subset from the broad-market scan receives five-year history forecasts.'} This is not a complete ranking of every stock in the market.</p>
        {plan.ranking_scope && <p className="mt-2 text-sm text-cyan-200" role="note">
          {plan.ranking_scope.market_symbols_screened !== null ? `${plan.ranking_scope.market_symbols_screened.toLocaleString()} symbols received the preliminary market scan. ` : ''}
          {plan.ranking_scope.preliminary_candidates_quality_screened !== null ? `${plan.ranking_scope.preliminary_candidates_quality_screened.toLocaleString()} preliminary candidates received additional quality screening. ` : ''}
          {plan.ranking_scope.symbols_with_estimates} of {plan.ranking_scope.symbols_selected_for_forecast} selected stocks have a historical growth estimate. The model has not forecast every stock.
        </p>}
        <p className="mt-2 text-xs text-amber-200">These percentage estimates describe approximately {plan.plan.forecast_horizon_sessions} trading sessions ({plan.plan.forecast_period}), not the entire {plan.plan.horizon === 'long' ? '5+ year' : plan.plan.horizon === 'medium' ? '1–5 year' : 'under-one-year'} holding period. A negative estimate is excluded from the money split, but is not a measured probability that the stock will fall.</p>
        {plan.ranked_stocks.length === 0 ? <p className="mt-5 text-slate-300">{plan.selection.note ? 'No individual-stock forecasts are available from this market scan.' : 'No stocks have enough history to estimate growth.'}</p> :
          <div className="mt-5 grid gap-4 lg:grid-cols-2">{plan.ranked_stocks.map(idea => <button type="button" key={idea.symbol}
            onClick={() => setChosen(idea.symbol)} aria-pressed={chosen === idea.symbol}
            className={`rounded-xl border p-4 text-left ${chosen === idea.symbol ? 'border-cyan-400 bg-slate-950' : 'border-slate-700 hover:bg-slate-800'}`}>
            <GrowthBar idea={idea} allocationNote={allocationNote(idea.symbol, idea.estimated_change_pct)}/>
          </button>)}</div>}
        <p className="mt-4 text-xs text-slate-400">The range shows outcomes of similar past patterns. It is not a calibrated probability or a promise of future results.</p>
      </div>
      {chosenIdea && preview.length > 0 ? <div className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
        <div className="flex items-baseline justify-between gap-2"><h2 className="text-xl font-bold">{chosenIdea.symbol}: past prices and possible future endpoint</h2>
          <Link className="text-xs text-emerald-300 underline" to={`/history?symbol=${encodeURIComponent(chosenIdea.symbol)}`}>Full history</Link></div>
        <div className="mt-3"><HistoryWithEstimatedEndpoint symbol={chosenIdea.symbol} history={preview} idea={chosenIdea}/></div>
        <div className="mt-4 flex flex-wrap gap-2 text-xs">
          <span className="rounded-lg border border-slate-700 px-3 py-2">Last adjusted close: {currency(chosenIdea.current_adjusted_price)}</span>
          <span className="rounded-lg border border-amber-700 px-3 py-2 text-amber-200">Experimental endpoint: {currency(chosenIdea.estimated_end_price_usd)}</span>
          <span className="rounded-lg border border-slate-700 px-3 py-2">Date of last price: {chosenIdea.as_of}</span>
        </div>
      </div> : null}
      <details className="rounded-xl border border-slate-700 bg-slate-900 p-5 text-xs text-slate-300">
        <summary className="cursor-pointer text-sm font-semibold text-white">Where these estimates come from and what could go wrong</summary>
        <p className="mt-3">{plan.important}</p><p className="mt-2">{plan.plan.warning}</p><p className="mt-2">{plan.history_source}</p>
        <p className="mt-2">Forecasts are tested on non-overlapping historical periods using only returns known at each test date. The selected current-day stocks may not represent stocks that existed or survived at older dates. No tested model can promise the best future stock or the safest selling time.</p>
      </details>
    </div>}
  </section>
}
