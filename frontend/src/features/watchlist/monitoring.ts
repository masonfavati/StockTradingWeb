import { isMarketSnapshot, type MarketSnapshot } from '../market/marketData'

export interface MonitoredStock extends MarketSnapshot {
  name: string
  subscription_status: 'confirmed' | 'pending'
}

export interface MonitoredFeed {
  provider: 'alpaca'
  feed: 'test' | 'iex'
  coverage: 'synthetic_test' | 'iex_only'
  connection_status: string
  free_stream_limit: number
  limited_symbols: string[]
  error: string | null
  stocks: MonitoredStock[]
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isMonitoredFeed(value: unknown): value is MonitoredFeed {
  if (!isRecord(value)) return false
  return (
    value.provider === 'alpaca' &&
    (value.feed === 'test' || value.feed === 'iex') &&
    (value.coverage === 'synthetic_test' || value.coverage === 'iex_only') &&
    typeof value.connection_status === 'string' &&
    typeof value.free_stream_limit === 'number' &&
    Number.isInteger(value.free_stream_limit) &&
    Array.isArray(value.limited_symbols) &&
    value.limited_symbols.every((item: unknown) => typeof item === 'string') &&
    (value.error === null || typeof value.error === 'string') &&
    Array.isArray(value.stocks) &&
    value.stocks.every((item: unknown) =>
      isMarketSnapshot(item) && isRecord(item) &&
      typeof item.name === 'string' &&
      (item.subscription_status === 'confirmed' ||
       item.subscription_status === 'pending'),
    )
  )
}

export type WatchStatus = 'demo' | 'offline' | 'limited' | 'waiting' | 'live' | 'stale'

export function stockStatus(
  symbol: string,
  feed: MonitoredFeed | null,
  browserConnected: boolean,
): WatchStatus {
  if (!browserConnected || feed === null) return 'offline'
  if (feed.feed === 'test') return 'demo'
  if (feed.limited_symbols.includes(symbol)) return 'limited'
  if (feed.connection_status !== 'connected') return 'offline'
  const stock = feed.stocks.find((item) => item.symbol === symbol)
  if (!stock || stock.subscription_status !== 'confirmed') return 'waiting'
  if (stock.connection_status !== 'connected') return 'offline'
  if (stock.data_status === 'live' && (stock.trade_fresh || stock.quote_fresh)) {
    return 'live'
  }
  if (stock.latest_trade || stock.latest_quote) return 'stale'
  return 'waiting'
}

export const statusDescriptions: Record<WatchStatus, string> = {
  demo: 'Demo mode — real stock prices are off',
  offline: 'Live feed unavailable',
  limited: 'Saved, but not monitored (free feed is full)',
  waiting: 'Waiting for an IEX market update',
  live: 'Recent IEX market data',
  stale: 'Last recorded data — not a current price',
}

export function formatObservationTime(value: string | undefined): string {
  if (!value) return 'No trade received'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Invalid time'
  return date.toLocaleString()
}
