import { describe, expect, it } from 'vitest'
import { buildPriceChartGeometry, percentSinceFirst } from './priceChartGeometry'
import { historyLink, validHistoryTicker, type StockHistoryResponse } from './historyApi'

const sample: StockHistoryResponse = {
  version: 'independent-stock-history-v1', symbol: 'AAA', period: '1m',
  provider: 'alpaca', feed: 'sip', adjustment: 'all', timeframe: '1Day',
  fetched_at_utc: '2026-11-15T20:00:00+00:00', provider_cutoff_utc: '2026-11-15T04:00:00+00:00',
  first_session: '2026-11-10', last_session: '2026-11-13', session_count: 3,
  first_adjusted_close_usd: 20, last_adjusted_close_usd: 24, period_change_pct: 20,
  benchmark_requested: true, benchmark_available: true,
  benchmark_anchor_session: '2026-11-10',
  bars: [
    { session_date: '2026-11-10', adjusted_close_usd: 20, normalized_index: 100 },
    { session_date: '2026-11-11', adjusted_close_usd: 22, normalized_index: 110 },
    { session_date: '2026-11-13', adjusted_close_usd: 24, normalized_index: 120 },
  ],
  spy_benchmark: [
    { session_date: '2026-11-10', normalized_index: 100 },
    { session_date: '2026-11-13', normalized_index: 103 },
  ],
  warning: null, price_forecast: null, forecast_status: 'no_validated_price_forecast',
  forecast_explanation: 'Not a share price forecast', caveat: 'Retrospective adjusted prices only.',
}

describe('historical chart math', () => {
  it('renders positive adjusted prices on a bounded SVG scale', () => {
    const graph = buildPriceChartGeometry(sample, false)
    expect(graph?.stock).toHaveLength(3)
    expect(graph?.spy).toHaveLength(0)
    expect(graph?.stock.every(p => Number.isFinite(p.x) && Number.isFinite(p.y))).toBe(true)
    expect(graph?.focusAt(2)).toEqual(graph?.stock[2])
  })
  it('never fabricates missing benchmark sessions', () => {
    const graph = buildPriceChartGeometry(sample, true)
    expect(graph?.spy).toHaveLength(2)
    expect(graph?.spy[0].x).toBe(graph?.stock[0].x)
    expect(graph?.spy[1].x).toBe(graph?.stock[2].x)
  })
  it('does not draw invalid or empty values as fake price movement', () => {
    expect(buildPriceChartGeometry({ ...sample, bars: [] }, false)).toBeNull()
    expect(buildPriceChartGeometry({ ...sample, bars: [
      { session_date: '2026-11-13', adjusted_close_usd: Number.NaN, normalized_index: 100 },
    ] }, false)).toBeNull()
  })
  it('renders display changes without interpreting them as predictions', () => {
    expect(percentSinceFirst(sample)).toBe('+20.00%')
    expect(percentSinceFirst({ ...sample, period_change_pct: -5.4 })).toBe('-5.40%')
    expect(percentSinceFirst({ ...sample, period_change_pct: null })).toBe('Unavailable')
  })
  it('links from research cards with safe historical signal dates', () => {
    expect(historyLink('aapl', '2026-11-13')).toBe('/history?symbol=AAPL&signal=2026-11-13')
    expect(historyLink('MSFT', '<bad>')).toBe('/history?symbol=MSFT')
    expect(validHistoryTicker(' BRK.B ')).toBe(true)
    expect(validHistoryTicker('AA;DROP')).toBe(false)
  })
})
