import { useMemo } from 'react'
import type { AllocationItem, GrowthIdea } from './investingApi'
import { currency } from './money'

const coreColor = '#38bdf8'
const cashColor = '#64748b'
const stockPalette = ['#34d399', '#fbbf24', '#a78bfa', '#fb7185', '#2dd4bf', '#f97316']

export function AllocationWheel({ allocations }: {allocations: AllocationItem[]}) {
  const colors = allocations.map((row, index) => {
    if (row.category === 'diversified_core') return coreColor
    if (row.category === 'cash') return cashColor
    // Count only earlier stock slices. Pure calculation: no mutation during render.
    const stockIndex = allocations.slice(0, index).filter(
      previous => previous.category === 'experimental_stock',
    ).length
    return stockPalette[stockIndex % stockPalette.length]
  })
  const parts = allocations.reduce<{color: string; from: number; to: number}[]>((acc, row, index) => {
    const from = acc.length ? acc[acc.length - 1].to : 0
    acc.push({color: colors[index], from, to: from + row.percent_of_budget})
    return acc
  }, [])
  const background = parts.length
    ? `conic-gradient(${parts.map(p => `${p.color} ${p.from}% ${p.to}%`).join(', ')})`
    : '#475569'
  return <div className="flex flex-wrap items-center gap-8">
    <div role="img" aria-label="Pie chart showing the budget split between individual stocks, diversified fund and cash"
      className="relative h-48 w-48 shrink-0 rounded-full" style={{background}}>
      <div className="absolute inset-10 flex items-center justify-center rounded-full bg-slate-900 text-center text-xs text-slate-300">
        Your budget<br />split
      </div>
    </div>
    <div className="min-w-52 flex-1 space-y-3">
      {allocations.map((row, index) => <div key={`${row.symbol ?? 'cash'}-${index}`}>
        <div className="flex items-center justify-between gap-2 text-sm">
          <span className="flex items-center gap-2 font-medium"><span className="h-3 w-3 rounded-sm" style={{background: colors[index]}} />
            {row.symbol ?? 'Cash'} {row.category === 'experimental_stock' && '(experimental)'}
          </span>
          <strong className="tabular-nums">{currency(row.amount_usd)}</strong>
        </div>
        <p className="ml-5 text-xs text-slate-400">{row.why}</p>
      </div>)}
    </div>
  </div>
}

export function GrowthBar({ idea, allocationNote }: {idea: GrowthIdea; allocationNote?: string}) {
  const left = Math.max(-60, Math.min(100, idea.historical_analogue_low_pct))
  const right = Math.max(left, Math.min(100, idea.historical_analogue_high_pct))
  const centre = Math.max(-60, Math.min(100, idea.estimated_change_pct))
  const pos = (value: number) => (value + 60) / 160 * 100
  return <div className="space-y-2">
    <div className="flex items-center justify-between gap-2">
      <span className="font-semibold">{idea.symbol}</span>
      <span className={`font-semibold tabular-nums ${idea.estimated_change_pct >= 0 ? 'text-emerald-300' : 'text-rose-300'}`}>
        {idea.estimated_change_pct > 0 ? '+' : ''}{idea.estimated_change_pct.toFixed(1)}% <span className="text-xs font-normal text-slate-400">estimated</span>
      </span>
    </div>
    <div role="img" aria-label={`${idea.symbol} experimental estimate ${idea.estimated_change_pct} percent, with historical analogues from ${idea.historical_analogue_low_pct} to ${idea.historical_analogue_high_pct} percent`}
      className="relative h-6 rounded-full bg-slate-800">
      <span className="absolute top-0 h-6 w-px bg-slate-400" style={{left: `${pos(0)}%`}} />
      <span className="absolute top-1.5 h-3 rounded-full bg-cyan-700/80" style={{left: `${pos(left)}%`, width: `${Math.max(1, pos(right) - pos(left))}%`}} />
      <span className="absolute top-0.5 h-5 w-1 rounded-full bg-white" style={{left: `${pos(centre)}%`}} />
    </div>
    <div className="flex justify-between text-xs text-slate-400"><span>Historical lower outcome: {idea.historical_analogue_low_pct}%</span><span>Upper: {idea.historical_analogue_high_pct}%</span></div>
    {allocationNote && <p className={`text-xs ${idea.estimated_change_pct <= 0 ? 'text-rose-300' : 'text-slate-300'}`}>{allocationNote}</p>}
    <p className="text-xs text-slate-400">{idea.similar_past_patterns_with_gain_pct !== undefined ? `${idea.similar_past_patterns_with_gain_pct}% of similar historical examples gained · ` : ""}{idea.backtest.disjoint_test_windows} completed historical checks · {idea.status === 'backtest_candidate' ? 'Beat its simple past baseline' : 'Has not beaten its simple baseline'}</p>
  </div>
}

export function HistoryWithEstimatedEndpoint({
  symbol, history, idea,
}: {symbol: string; history: {date: string; adjusted_close: number}[]; idea: GrowthIdea}) {
  const points = useMemo(() => {
    const prices = history.map(p => p.adjusted_close).filter(v => Number.isFinite(v) && v > 0)
    if (prices.length < 3) return null
    const low = Math.min(...prices, idea.analogue_low_price_usd, idea.estimated_end_price_usd)
    const high = Math.max(...prices, idea.analogue_high_price_usd, idea.estimated_end_price_usd)
    const spread = Math.max(0.0001, high - low)
    const y = (v: number) => 192 - (v - low) / spread * 159
    const path = prices.map((v, i) => `${i === 0 ? 'M' : 'L'}${20 + i / (prices.length - 1) * 390},${y(v).toFixed(1)}`).join(' ')
    return {path, current: y(prices[prices.length - 1]), projected: y(idea.estimated_end_price_usd),
      lower: y(idea.analogue_low_price_usd), upper: y(idea.analogue_high_price_usd)}
  }, [history, idea])
  if (!points) return <p className="text-sm text-slate-400">Not enough historical chart points available.</p>
  return <div>
    <svg viewBox="0 0 690 235" role="img" aria-label={`${symbol} past prices shown as solid line, with separate experimental future endpoint range; no intermediate future prices are predicted`}
      className="w-full rounded-xl bg-slate-950">
      <line x1="420" y1="12" x2="420" y2="205" stroke="#94a3b8" strokeDasharray="4 5" />
      <path d={points.path} fill="none" stroke="#34d399" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
      <circle cx="410" cy={points.current} r="5" fill="#f8fafc" />
      <rect x="582" width="56" y={Math.min(points.upper, points.lower)}
        height={Math.max(4, Math.abs(points.upper - points.lower))} rx="8" fill="#38bdf8" opacity="0.27" />
      <line x1="610" y1={points.upper} x2="610" y2={points.lower} stroke="#38bdf8" strokeWidth="2" />
      <circle cx="610" cy={points.projected} r="6" fill="#facc15" stroke="#fff" />
      <text x="22" y="220" fill="#cbd5e1" fontSize="13">Actual past daily prices</text>
      <text x="412" y="18" fill="#cbd5e1" fontSize="12">Last observed</text>
      <text x="540" y="220" fill="#cbd5e1" fontSize="12">Future endpoint</text>
      <text x="460" y="45" fill="#facc15" fontSize="12">Experimental range</text>
    </svg>
    <p className="mt-2 text-xs text-slate-400">Solid line = recorded history. Shaded band and yellow dot = experimental outcome estimates at the selected horizon, not a predicted price path or guaranteed range.</p>
  </div>
}
