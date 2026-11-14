import { describe, expect, it } from 'vitest'
import {
  displayPrice,
  getDataLabel,
  isMarketSnapshot,
  type MarketSnapshot,
} from './marketData'

const snapshot: MarketSnapshot = {
  provider: 'alpaca',
  feed: 'iex',
  symbol: 'AAPL',
  coverage: 'iex_only',
  connection_status: 'connected',
  data_status: 'live',
  trade_fresh: true,
  quote_fresh: false,
  trade_age_seconds: 1,
  quote_age_seconds: null,
  received_at: '2026-11-13T15:00:00Z',
  error: null,
  latest_trade: {
    price: '150.1234',
    size: 10,
    timestamp: '2026-11-13T15:00:00Z',
  },
  latest_quote: null,
}

describe('Market-data integrity', () => {
  it('recognizes a valid snapshot', () => {
    expect(isMarketSnapshot(snapshot)).toBe(true)
  })

  it('rejects invalid market observations', () => {
    expect(isMarketSnapshot({ ...snapshot, trade_fresh: 'yes' }))
      .toBe(false)
  })

  it('does not label simulated data as live', () => {
    const fake = {
      ...snapshot,
      feed: 'test' as const,
      data_status: 'simulated',
    }

    expect(getDataLabel(fake, 'connected')).toBe('SIMULATED DATA')
  })

  it('does not label disconnected feeds as live', () => {
    expect(getDataLabel(snapshot, 'reconnecting'))
      .toBe('STREAM DISCONNECTED')
  })

  it('distinguishes stale observations', () => {
    const stale = {
      ...snapshot,
      data_status: 'stale',
      trade_fresh: false,
    }

    expect(getDataLabel(stale, 'connected')).toBe('STALE DATA')
  })

  it('preserves market-price decimal text', () => {
    expect(displayPrice('150.1234')).toBe('$150.1234')
  })
})
