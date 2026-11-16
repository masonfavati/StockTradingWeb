import type { StockHistoryResponse } from './historyApi'

export const CHART_WIDTH = 980
export const CHART_HEIGHT = 330
const LEFT = 66
const RIGHT = 18
const TOP = 18
const BOTTOM = 42
const PLOT_W = CHART_WIDTH - LEFT - RIGHT
const PLOT_H = CHART_HEIGHT - TOP - BOTTOM

export interface Point { x: number; y: number }
export interface ChartGeometry {
  stock: Point[]
  spy: Point[]
  ticks: { y: number; value: number }[]
  zeroX: number
  xAt: (index: number) => number
  focusAt: (index: number) => Point | null
}

export function buildPriceChartGeometry(data: StockHistoryResponse, compare: boolean): ChartGeometry | null {
  const bars = data.bars
  if (bars.length === 0) return null
  const values = bars.map(p => compare ? p.normalized_index : p.adjusted_close_usd)
  const spies = compare && data.benchmark_available ? data.spy_benchmark : []
  const all = [...values, ...spies.map(row => row.normalized_index)]
  if (!all.every(v => Number.isFinite(v) && v > 0)) return null
  const lo = Math.min(...all)
  const hi = Math.max(...all)
  const pad = Math.max((hi - lo) * 0.1, hi * 0.003)
  const min = Math.max(0, lo - pad)
  const max = hi + pad
  const xAt = (index: number) => LEFT + (bars.length <= 1 ? PLOT_W / 2 : index * PLOT_W / (bars.length - 1))
  const yAt = (value: number) => TOP + (max - value) / (max - min) * PLOT_H
  const stock = values.map((value, i) => ({ x: xAt(i), y: yAt(value) }))
  const dates = new Map(bars.map((row, i) => [row.session_date, i]))
  const spy = spies.flatMap(point => {
    const index = dates.get(point.session_date)
    return index === undefined ? [] : [{ x: xAt(index), y: yAt(point.normalized_index) }]
  })
  return {
    stock, spy,
    ticks: Array.from({ length: 5 }, (_, i) => {
      const value = min + (max - min) * i / 4
      return { y: yAt(value), value }
    }),
    zeroX: LEFT,
    xAt,
    focusAt: (index) => stock[index] ?? null,
  }
}

export const asSvgPolyline = (points: Point[]) => points.map(p => `${p.x.toFixed(2)},${p.y.toFixed(2)}`).join(' ')

export function percentSinceFirst(data: StockHistoryResponse): string {
  if (data.period_change_pct === null) return 'Unavailable'
  const value = data.period_change_pct
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}
