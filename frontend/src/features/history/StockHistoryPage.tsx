import { useEffect, useMemo, useState, type FormEvent, type MouseEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { getStockHistory, type HistoryPeriod, type StockHistoryResponse, validHistoryTicker } from './historyApi'
import BeginnerHelp from '../learn/BeginnerHelp'
import { asSvgPolyline, buildPriceChartGeometry, CHART_HEIGHT, CHART_WIDTH, percentSinceFirst } from './priceChartGeometry'

const periods: { value: HistoryPeriod; label: string }[] = [
  { value: '1m', label: '1 month' }, { value: '3m', label: '3 months' },
  { value: '1y', label: '1 year' }, { value: '5y', label: '5 years' },
]
const money = (value: number) => `$${value.toLocaleString('en-US', { minimumFractionDigits: value < 0.01 ? 8 : 2, maximumFractionDigits: value < 0.01 ? 8 : 4 })}`

export default function StockHistoryPage() {
  const [query, setQuery] = useSearchParams()
  const symbol = (query.get('symbol') ?? 'SPY').trim().toUpperCase()
  const signal = query.get('signal')
  const [draftEntry, setDraftEntry] = useState({ symbol, value: symbol })
  const draft = draftEntry.symbol === symbol ? draftEntry.value : symbol
  const [period, setPeriod] = useState<HistoryPeriod>('1y')
  const [compareSpy, setCompareSpy] = useState(false)
  const requestKey = `${symbol}:${period}:${compareSpy}`
  const [historyResult, setHistoryResult] = useState<{
    key: string
    data: StockHistoryResponse | null
    error: string | null
  } | null>(null)
  const currentResult = historyResult?.key === requestKey ? historyResult : null
  const data = currentResult?.data ?? null
  const loading = validHistoryTicker(symbol) && currentResult === null
  const error = validHistoryTicker(symbol)
    ? (currentResult?.error ?? null)
    : 'Enter one valid US stock ticker (for example, AAPL).'
  const [focus, setFocus] = useState(0)
  const [validationError, setValidationError] = useState<string | null>(null)

  useEffect(() => {
    if (!validHistoryTicker(symbol)) return
    const controller = new AbortController()
    let active = true
    void getStockHistory(symbol, period, compareSpy, controller.signal).then(result => {
      if (active) {
        setHistoryResult({ key: requestKey, data: result, error: null })
        setFocus(Math.max(0, result.bars.length - 1))
      }
    }).catch(cause => {
      if (active && !(cause instanceof Error && cause.name === 'AbortError')) {
        setHistoryResult({
          key: requestKey,
          data: null,
          error: cause instanceof Error ? cause.message : 'Historical prices are unavailable.',
        })
      }
    })
    return () => { active = false; controller.abort() }
  }, [symbol, period, compareSpy, requestKey])

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const normalized = draft.trim().toUpperCase()
    if (!validHistoryTicker(normalized)) {
      setValidationError('Enter one ticker using letters, numbers, dots, or hyphens.')
      return
    }
    setValidationError(null)
    setCompareSpy(false)
    setQuery({ symbol: normalized })
  }

  const geometry = useMemo(() => data ? buildPriceChartGeometry(data, compareSpy) : null, [data, compareSpy])
  const index = data ? Math.min(focus, Math.max(0, data.bars.length - 1)) : 0
  const hovered = data?.bars[index]
  const spyValue = hovered ? data?.spy_benchmark.find(row => row.session_date === hovered.session_date)?.normalized_index : undefined
  const markerIndex = data && signal && /^\d{4}-\d{2}-\d{2}$/.test(signal)
    ? data.bars.findIndex(p => p.session_date === signal) : -1
  const primaryUp = (data?.period_change_pct ?? 0) >= 0
  const highIndex = data?.historical_insights?.highest_date
    ? data.bars.findIndex(point => point.session_date === data.historical_insights?.highest_date) : -1
  const lowIndex = data?.historical_insights?.lowest_date
    ? data.bars.findIndex(point => point.session_date === data.historical_insights?.lowest_date) : -1

  function moveFocus(event: MouseEvent<SVGSVGElement>) {
    if (!data?.bars.length) return
    const rect = event.currentTarget.getBoundingClientRect()
    if (rect.width <= 0) return
    const coordinate = (event.clientX - rect.left) / rect.width * CHART_WIDTH
    const value = Math.round((coordinate - 66) / (CHART_WIDTH - 66 - 18) * (data.bars.length - 1))
    setFocus(Math.max(0, Math.min(data.bars.length - 1, value)))
  }

  return <section className="space-y-6" aria-label="Independent stock price history">
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-8">
      <p className="text-sm font-semibold text-emerald-400">Understand a stock through its history</p>
      <h1 className="mt-2 text-3xl font-bold">See how a stock has actually moved</h1>
      <p className="mt-3 max-w-4xl text-sm text-slate-300">
        Look up a stock and see what its price did in the past. You do not need to run
        Find Opportunities first. This page loads earlier prices directly from the data provider.
      </p>
      <form onSubmit={submit} className="mt-5 flex max-w-xl flex-wrap items-end gap-3">
        <label className="flex-1 text-sm font-medium">Stock symbol (ticker)
          <input value={draft} onChange={e => setDraftEntry({ symbol, value: e.target.value })} aria-label="Stock symbol (ticker)"
            placeholder="AAPL, MSFT, SPY…" maxLength={22}
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-white" />
        </label>
        <button type="submit" className="rounded-lg bg-emerald-600 px-5 py-3 font-semibold text-white hover:bg-emerald-500">
          Show history
        </button>
      </form>
      {validationError && <p className="mt-3 text-sm text-red-300" role="alert">{validationError}</p>}
      <p className="mt-3 text-xs text-slate-400">Example: AAPL means Apple. Looking up a stock does not buy it.</p>
    </div>

    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold">{symbol} · past share prices</h2>
          <p className="mt-1 text-xs text-slate-400">Past end-of-day prices, adjusted for stock splits and payouts. Not today’s buying price.</p>
        </div>
        <fieldset className="flex flex-wrap gap-2" aria-label="History period">
          <legend className="sr-only">History period</legend>
          {periods.map(option => <button type="button" key={option.value}
            aria-pressed={period === option.value}
            onClick={() => setPeriod(option.value)}
            className={`rounded-lg border px-3 py-2 text-sm ${period === option.value
              ? 'border-emerald-500 bg-emerald-900/30 text-emerald-200'
              : 'border-slate-700 text-slate-300 hover:bg-slate-800'}`}>{option.label}</button>)}
        </fieldset>
      </div>
      <p className="mt-4 text-sm text-slate-300">How to read the graph: a rising line means the displayed price rose; a falling line means it fell. Nothing to the right of today is predicted.</p>
      <label className="mt-5 flex items-center gap-2 text-sm text-slate-300">
        <input type="checkbox" checked={compareSpy} onChange={e => setCompareSpy(e.target.checked)}
          aria-label="Compare with SPY" disabled={symbol === 'SPY'} />
        Compare with SPY, a fund holding many large U.S. stocks (both lines start at 100)
      </label>

      {loading && <p className="mt-8 text-slate-300" role="status">Loading past stock prices…</p>}
      {error && <p className="mt-8 rounded-xl border border-red-800 p-4 text-red-300" role="alert">{error}</p>}
      {data && <>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <p className="text-xs text-slate-400">Last recorded daily price (adjusted)</p>
            <p className="mt-1 text-xl font-semibold">{data.last_adjusted_close_usd === null ? 'Unavailable' : money(data.last_adjusted_close_usd)}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <p className="text-xs text-slate-400">How much the price changed</p>
            <p className={`mt-1 text-xl font-semibold ${primaryUp ? 'text-emerald-300' : 'text-rose-300'}`}>{percentSinceFirst(data)}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <p className="text-xs text-slate-400">Date of the last price</p>
            <p className="mt-1 text-xl font-semibold">{data.last_session ?? 'Unavailable'}</p>
          </div>
        </div>
        {data.historical_insights && data.session_count > 0 && <section className="mt-5 rounded-xl border border-slate-700 p-4" aria-label="Historical price story">
          <h3 className="text-lg font-semibold">What happened during these dates?</h3>
          <p className="mt-2 text-sm text-slate-300">These figures describe the past—not what will happen next.</p>
          <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            <div className="rounded-lg bg-slate-950 p-3"><p className="text-xs text-slate-400">Highest recorded price</p>
              <p className="mt-1 font-semibold">{data.historical_insights.highest_price_usd === null ? 'Not available' : money(data.historical_insights.highest_price_usd)}</p>
              <p className="text-xs text-slate-400">{data.historical_insights.highest_date}</p></div>
            <div className="rounded-lg bg-slate-950 p-3"><p className="text-xs text-slate-400">Lowest recorded price</p>
              <p className="mt-1 font-semibold">{data.historical_insights.lowest_price_usd === null ? 'Not available' : money(data.historical_insights.lowest_price_usd)}</p>
              <p className="text-xs text-slate-400">{data.historical_insights.lowest_date}</p></div>
            <div className="rounded-lg bg-slate-950 p-3"><p className="text-xs text-slate-400">Biggest fall after an earlier high</p>
              <p className="mt-1 font-semibold">{data.historical_insights.largest_drop_from_previous_high_pct === null ? 'Not enough data' : `${data.historical_insights.largest_drop_from_previous_high_pct.toFixed(2)}%`}</p>
              <p className="text-xs text-slate-400">Within the selected dates, not a worst-case prediction</p></div>
            <div className="rounded-lg bg-slate-950 p-3"><p className="text-xs text-slate-400">Average move between recorded days</p>
              <p className="mt-1 font-semibold">{data.historical_insights.average_change_between_recorded_days_pct === null ? 'Not enough data' : `${data.historical_insights.average_change_between_recorded_days_pct.toFixed(2)}%`}</p>
              <p className="text-xs text-slate-400">Counts both rises and falls</p></div>
          </div>
          <p className="mt-3 text-sm text-slate-300">Between the dates shown, prices rose on {data.historical_insights.up_days} recorded intervals, fell on {data.historical_insights.down_days}, and stayed the same on {data.historical_insights.flat_days}.</p>
          {data.historical_insights.spy_change_pct !== null && <p className="mt-2 text-sm text-slate-300">
            Over the matching dates, SPY changed {data.historical_insights.spy_change_pct > 0 ? '+' : ''}{data.historical_insights.spy_change_pct.toFixed(2)}%.
            {' '}{symbol} moved {data.historical_insights.difference_vs_spy_percentage_points === null ? 'an unknown amount' : `${Math.abs(data.historical_insights.difference_vs_spy_percentage_points).toFixed(2)} percentage points ${data.historical_insights.difference_vs_spy_percentage_points >= 0 ? 'more' : 'less'}`} than SPY.
            This compares historical price changes, not real investment profits.
          </p>}
        </section>}
        {data.warning && <p className="mt-4 text-sm text-amber-200" role="status">{data.warning}</p>}
        {geometry && <>
          <div className="mt-6 overflow-x-auto rounded-lg border border-slate-800 bg-slate-950 p-2">
            <svg viewBox={`0 0 ${CHART_WIDTH} ${CHART_HEIGHT}`} className="block w-full min-w-[370px]"
              role="img" aria-label={`${symbol} historical ${compareSpy ? 'indexed performance compared with SPY' : 'adjusted share closing price'} chart`}
              onMouseMove={moveFocus}>
              {geometry.ticks.map((tick, i) => <g key={i}>
                <line x1={66} x2={CHART_WIDTH - 18} y1={tick.y} y2={tick.y} stroke="#334155" strokeWidth="1" />
                <text x={58} y={tick.y + 4} textAnchor="end" fill="#94a3b8" fontSize="12">
                  {compareSpy ? tick.value.toFixed(1) : `$${tick.value.toFixed(1)}`}
                </text>
              </g>)}
              {markerIndex >= 0 && <g>
                <line x1={geometry.xAt(markerIndex)} x2={geometry.xAt(markerIndex)} y1={18} y2={CHART_HEIGHT - 42}
                  stroke="#fbbf24" strokeDasharray="5 5" strokeWidth="2" />
                <text x={Math.min(geometry.xAt(markerIndex) + 5, CHART_WIDTH - 160)} y={24} fill="#fbbf24" fontSize="12">Market search date</text>
              </g>}
              {geometry.spy.length > 1 && <polyline fill="none" stroke="#94a3b8" strokeWidth="2.5"
                vectorEffect="non-scaling-stroke" points={asSvgPolyline(geometry.spy)} />}
              {geometry.stock.length > 1 && <polyline fill="none" stroke="#34d399" strokeWidth="2.5"
                vectorEffect="non-scaling-stroke" points={asSvgPolyline(geometry.stock)} />}
              {highIndex >= 0 && geometry.focusAt(highIndex) && <g>
                <circle cx={geometry.focusAt(highIndex)?.x} cy={geometry.focusAt(highIndex)?.y}
                  r="6" fill="#fbbf24" stroke="#0f172a" strokeWidth="2" />
                <title>Highest adjusted price on {data.historical_insights?.highest_date}</title>
              </g>}
              {lowIndex >= 0 && lowIndex !== highIndex && geometry.focusAt(lowIndex) && <g>
                <circle cx={geometry.focusAt(lowIndex)?.x} cy={geometry.focusAt(lowIndex)?.y}
                  r="6" fill="#fb7185" stroke="#0f172a" strokeWidth="2" />
                <title>Lowest adjusted price on {data.historical_insights?.lowest_date}</title>
              </g>}
              {geometry.focusAt(index) && <circle cx={geometry.focusAt(index)?.x} cy={geometry.focusAt(index)?.y} r="5" fill="#6ee7b7" stroke="#0f172a" strokeWidth="2" />}
              <text x={66} y={CHART_HEIGHT - 12} fill="#94a3b8" fontSize="12">{data.first_session}</text>
              <text x={CHART_WIDTH - 18} y={CHART_HEIGHT - 12} textAnchor="end" fill="#94a3b8" fontSize="12">{data.last_session}</text>
            </svg>
          </div>
          <div className="mt-3 flex flex-wrap gap-5 text-xs text-slate-300">
            <span><span className="text-emerald-300">●</span> {symbol} past prices</span>
            {compareSpy && data.benchmark_available && <span><span className="text-slate-400">●</span> SPY comparison</span>}
            {markerIndex >= 0 && <span className="text-amber-200">┆ Market search date</span>}
            {highIndex >= 0 && <span><span className="text-amber-300">●</span> Highest shown price</span>}
            {lowIndex >= 0 && lowIndex !== highIndex && <span><span className="text-rose-300">●</span> Lowest shown price</span>}
          </div>
          <div className="mt-5 rounded-lg border border-slate-700 p-4">
            <label className="block text-sm font-medium" htmlFor="inspect-history-session">Move the slider to inspect a day</label>
            <input id="inspect-history-session" aria-label="Inspect historical session" type="range"
              min="0" max={Math.max(0, data.bars.length - 1)} value={index}
              onChange={event => setFocus(Number(event.target.value))} className="mt-3 w-full accent-emerald-500" />
            {hovered && <p className="mt-2 text-sm text-slate-200" role="status">
              {hovered.session_date} · {symbol} past price: <strong>{money(hovered.adjusted_close_usd)}</strong>
              {compareSpy && <> · {symbol} index: {hovered.normalized_index.toFixed(2)}
                {spyValue === undefined ? ' · No SPY price for this date' : ` · SPY index: ${spyValue.toFixed(2)}`}</>}
            </p>}
          </div>
        </>}
        {!data.bars.length && <p className="mt-6 text-sm text-slate-300">We could not find earlier prices for this stock and date range. Try a different period or symbol.</p>}
        <p className="mt-4 text-xs text-slate-400">
          {data.session_count} recorded trading days · {data.first_session ?? 'unknown'} through {data.last_session ?? 'unknown'}
          {' '}· Prices provided by Alpaca · Checked {data.fetched_at_utc}.
        </p>
        <BeginnerHelp words={['stock', 'ticker', 'adjusted', 'change', 'index', 'spy', 'daily', 'drop']} />
        <details className="mt-3 text-xs text-slate-400"><summary className="cursor-pointer text-slate-300">Data source and important technical limits</summary><p className="mt-2">{data.caveat}</p></details>
      </>}
    </div>

    <div className="rounded-xl border border-amber-900 bg-slate-900 p-6">
      <h2 className="text-lg font-semibold text-amber-200">Can the website show where this price might go next?</h2>
      <p className="mt-2 text-sm text-slate-300">
        Not reliably yet. The experimental model asks whether a stock might do <strong>better than SPY</strong>
        over roughly 20 trading days. It cannot tell us a future share price, or even whether the stock
        will make money. We will only add a future-price line after a separate model proves useful
        on real results that were not known when it made its predictions.
      </p>
      <p className="mt-3 text-xs text-amber-200">No future price line or invented confidence interval is displayed.</p>
      <Link to="/forecasts" className="mt-3 inline-block text-sm text-emerald-400 underline">See how we test the predictions</Link>
    </div>
    <div className="flex flex-wrap gap-3 text-sm">
      <Link to="/decisions" className="rounded-lg border border-slate-600 px-4 py-2 text-slate-200 hover:bg-slate-800">Understand Stock Ideas</Link>
      <Link to="/planner" className="rounded-lg border border-slate-600 px-4 py-2 text-slate-200 hover:bg-slate-800">Plan a Budget</Link>
    </div>
  </section>
}
