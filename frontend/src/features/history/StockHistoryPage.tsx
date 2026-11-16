import { useEffect, useMemo, useState, type FormEvent, type MouseEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import { getStockHistory, type HistoryPeriod, type StockHistoryResponse, validHistoryTicker } from './historyApi'
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
      <p className="text-sm font-semibold text-emerald-400">Historical stock explorer</p>
      <h1 className="mt-2 text-3xl font-bold">See how a stock has actually moved</h1>
      <p className="mt-3 max-w-4xl text-sm text-slate-300">
        Explore completed daily price history for any supported ticker, even if you have never
        clicked Find Opportunities. The chart requests separate Alpaca historical data, not saved scanner snapshots.
      </p>
      <form onSubmit={submit} className="mt-5 flex max-w-xl flex-wrap items-end gap-3">
        <label className="flex-1 text-sm font-medium">Stock ticker
          <input value={draft} onChange={e => setDraftEntry({ symbol, value: e.target.value })} aria-label="Stock ticker"
            placeholder="AAPL, MSFT, SPY…" maxLength={22}
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-4 py-3 text-white" />
        </label>
        <button type="submit" className="rounded-lg bg-emerald-600 px-5 py-3 font-semibold text-white hover:bg-emerald-500">
          Show history
        </button>
      </form>
      {validationError && <p className="mt-3 text-sm text-red-300" role="alert">{validationError}</p>}
      <p className="mt-3 text-xs text-slate-400">You can search for a stock directly; scanning the market first is not required.</p>
    </div>

    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-5 sm:p-7">
      <div className="flex flex-wrap items-center justify-between gap-4">
        <div>
          <h2 className="text-2xl font-semibold">{symbol} · historical adjusted closes</h2>
          <p className="mt-1 text-xs text-slate-400">Daily SIP data · corporate-action-adjusted · not a live quote</p>
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
      <label className="mt-5 flex items-center gap-2 text-sm text-slate-300">
        <input type="checkbox" checked={compareSpy} onChange={e => setCompareSpy(e.target.checked)}
          aria-label="Compare with SPY" disabled={symbol === 'SPY'} />
        Compare percentage changes with SPY (both start at index 100)
      </label>

      {loading && <p className="mt-8 text-slate-300" role="status">Retrieving independent historical prices…</p>}
      {error && <p className="mt-8 rounded-xl border border-red-800 p-4 text-red-300" role="alert">{error}</p>}
      {data && <>
        <div className="mt-5 grid gap-3 sm:grid-cols-3">
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <p className="text-xs text-slate-400">Last adjusted historical close</p>
            <p className="mt-1 text-xl font-semibold">{data.last_adjusted_close_usd === null ? 'Unavailable' : money(data.last_adjusted_close_usd)}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <p className="text-xs text-slate-400">Change across displayed dates</p>
            <p className={`mt-1 text-xl font-semibold ${primaryUp ? 'text-emerald-300' : 'text-rose-300'}`}>{percentSinceFirst(data)}</p>
          </div>
          <div className="rounded-xl border border-slate-800 bg-slate-950 p-4">
            <p className="text-xs text-slate-400">Latest completed bar</p>
            <p className="mt-1 text-xl font-semibold">{data.last_session ?? 'Unavailable'}</p>
          </div>
        </div>
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
                <text x={Math.min(geometry.xAt(markerIndex) + 5, CHART_WIDTH - 160)} y={24} fill="#fbbf24" fontSize="12">Recorded scan date</text>
              </g>}
              {geometry.spy.length > 1 && <polyline fill="none" stroke="#94a3b8" strokeWidth="2.5"
                vectorEffect="non-scaling-stroke" points={asSvgPolyline(geometry.spy)} />}
              {geometry.stock.length > 1 && <polyline fill="none" stroke="#34d399" strokeWidth="2.5"
                vectorEffect="non-scaling-stroke" points={asSvgPolyline(geometry.stock)} />}
              {geometry.focusAt(index) && <circle cx={geometry.focusAt(index)?.x} cy={geometry.focusAt(index)?.y} r="5" fill="#6ee7b7" stroke="#0f172a" strokeWidth="2" />}
              <text x={66} y={CHART_HEIGHT - 12} fill="#94a3b8" fontSize="12">{data.first_session}</text>
              <text x={CHART_WIDTH - 18} y={CHART_HEIGHT - 12} textAnchor="end" fill="#94a3b8" fontSize="12">{data.last_session}</text>
            </svg>
          </div>
          <div className="mt-3 flex flex-wrap gap-5 text-xs text-slate-300">
            <span><span className="text-emerald-300">●</span> {symbol} adjusted closes</span>
            {compareSpy && data.benchmark_available && <span><span className="text-slate-400">●</span> SPY indexed comparison</span>}
            {markerIndex >= 0 && <span className="text-amber-200">┆ Recorded scanner session</span>}
          </div>
          <div className="mt-5 rounded-lg border border-slate-700 p-4">
            <label className="block text-sm font-medium" htmlFor="inspect-history-session">Inspect any historical trading day</label>
            <input id="inspect-history-session" aria-label="Inspect historical session" type="range"
              min="0" max={Math.max(0, data.bars.length - 1)} value={index}
              onChange={event => setFocus(Number(event.target.value))} className="mt-3 w-full accent-emerald-500" />
            {hovered && <p className="mt-2 text-sm text-slate-200" role="status">
              {hovered.session_date} · {symbol} adjusted close: <strong>{money(hovered.adjusted_close_usd)}</strong>
              {compareSpy && <> · {symbol} index: {hovered.normalized_index.toFixed(2)}
                {spyValue === undefined ? ' · SPY: no matched bar' : ` · SPY index: ${spyValue.toFixed(2)}`}</>}
            </p>}
          </div>
        </>}
        {!data.bars.length && <p className="mt-6 text-sm text-slate-300">No historical daily prices were returned for this ticker and range. Try another period or symbol.</p>}
        <p className="mt-4 text-xs text-slate-400">
          {data.session_count} actual sessions · {data.first_session ?? 'unknown'} through {data.last_session ?? 'unknown'}
          {' '}· Source: Alpaca SIP daily bars · Retrieved {data.fetched_at_utc}.
        </p>
        <p className="mt-2 text-xs text-slate-400">{data.caveat}</p>
      </>}
    </div>

    <div className="rounded-xl border border-amber-900 bg-slate-900 p-6">
      <h2 className="text-lg font-semibold text-amber-200">Where does the prediction think the price will go?</h2>
      <p className="mt-2 text-sm text-slate-300">
        The current prospective prediction model estimates the chance that a qualified stock will
        <strong> outperform SPY over 20 trading sessions</strong>—not an expected future share price.
        A probability of relative outperformance cannot be drawn honestly as a future price line.
        We will display a forward price projection here only after a separate price-and-uncertainty model is validated.
      </p>
      <p className="mt-3 text-xs text-amber-200">No future price line or invented confidence interval is displayed.</p>
      <Link to="/forecasts" className="mt-3 inline-block text-sm text-emerald-400 underline">Read the prospective model's validation evidence</Link>
    </div>
    <div className="flex flex-wrap gap-3 text-sm">
      <Link to="/decisions" className="rounded-lg border border-slate-600 px-4 py-2 text-slate-200 hover:bg-slate-800">Return to Research Decision Desk</Link>
      <Link to="/planner" className="rounded-lg border border-slate-600 px-4 py-2 text-slate-200 hover:bg-slate-800">Open the Investment Planner</Link>
    </div>
  </section>
}
