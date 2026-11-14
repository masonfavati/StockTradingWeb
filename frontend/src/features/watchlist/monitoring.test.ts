import { describe, expect, it } from 'vitest'
import { isMonitoredFeed, stockStatus, type MonitoredFeed } from './monitoring'

const sample: MonitoredFeed = {
  provider: 'alpaca',
  feed: 'iex',
  coverage: 'iex_only',
  connection_status: 'connected',
  free_stream_limit: 30,
  limited_symbols: [],
  error: null,
  stocks: [{
    provider: 'alpaca', feed: 'iex', symbol: 'AAPL', name: 'Apple Inc.',
    coverage: 'iex_only', connection_status: 'connected',
    data_status: 'live', trade_fresh: true, quote_fresh: false,
    trade_age_seconds: 1, quote_age_seconds: null, received_at: null,
    error: null, subscription_status: 'confirmed',
    latest_trade: { price: '200.1234', size: 10, timestamp: '2026-11-13T15:00:00Z' },
    latest_quote: null,
  }],
}

describe('Watchlist market-data integrity', () => {
  it('accepts a valid multi-stock snapshot', () => {
    expect(isMonitoredFeed(sample)).toBe(true)
  })

  it('rejects malformed snapshots', () => {
    expect(isMonitoredFeed({ ...sample, stocks: [{ symbol: 'AAPL' }] })).toBe(false)
  })

  it('recognizes a fresh, confirmed IEX observation', () => {
    expect(stockStatus('AAPL', sample, true)).toBe('live')
  })

  it('does not treat connection loss as live', () => {
    expect(stockStatus('AAPL', sample, false)).toBe('offline')
  })

  it('does not treat unconfirmed subscriptions as live', () => {
    expect(stockStatus('AAPL', {
      ...sample, stocks: [{ ...sample.stocks[0], subscription_status: 'pending' }],
    }, true)).toBe('waiting')
  })

  it('labels a free-tier overflow explicitly', () => {
    expect(stockStatus('MSFT', { ...sample, limited_symbols: ['MSFT'] }, true))
      .toBe('limited')
  })

  it('never maps synthetic FAKEPACA data to a real stock', () => {
    expect(stockStatus('AAPL', { ...sample, feed: 'test' }, true)).toBe('demo')
  })

  it('shows old records as stale', () => {
    expect(stockStatus('AAPL', {
      ...sample, stocks: [{ ...sample.stocks[0], data_status: 'stale', trade_fresh: false }],
    }, true)).toBe('stale')
  })
})
