export type StreamConnection =
  | 'connecting'
  | 'connected'
  | 'reconnecting'
  | 'disconnected'
  | 'unsupported'

export interface MarketSnapshot {
  provider: string
  feed: 'test' | 'iex'
  symbol: string
  coverage: string
  connection_status: string
  data_status: string
  trade_fresh: boolean
  quote_fresh: boolean
  trade_age_seconds: number | null
  quote_age_seconds: number | null
  received_at: string | null
  error: string | null
  latest_trade: {
    price: string
    size: number
    timestamp: string
  } | null
  latest_quote: {
    bid: string
    ask: string
    bid_size: number
    ask_size: number
    timestamp: string
  } | null
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}

export function isMarketSnapshot(value: unknown): value is MarketSnapshot {
  if (!isRecord(value)) return false

  const trade = value.latest_trade
  const quote = value.latest_quote

  return (
    value.provider === 'alpaca' &&
    (value.feed === 'iex' || value.feed === 'test') &&
    typeof value.symbol === 'string' &&
    typeof value.coverage === 'string' &&
    typeof value.connection_status === 'string' &&
    typeof value.data_status === 'string' &&
    typeof value.trade_fresh === 'boolean' &&
    typeof value.quote_fresh === 'boolean' &&
    (value.trade_age_seconds === null ||
      typeof value.trade_age_seconds === 'number') &&
    (value.quote_age_seconds === null ||
      typeof value.quote_age_seconds === 'number') &&
    (value.received_at === null ||
      typeof value.received_at === 'string') &&
    (value.error === null ||
      typeof value.error === 'string') &&
    (trade === null ||
      (isRecord(trade) &&
        typeof trade.price === 'string' &&
        typeof trade.size === 'number' &&
        typeof trade.timestamp === 'string')) &&
    (quote === null ||
      (isRecord(quote) &&
        typeof quote.bid === 'string' &&
        typeof quote.ask === 'string' &&
        typeof quote.bid_size === 'number' &&
        typeof quote.ask_size === 'number' &&
        typeof quote.timestamp === 'string'))
  )
}

export function getDataLabel(
  snapshot: MarketSnapshot | null,
  connection: StreamConnection,
): string {
  if (connection === 'connecting') return 'CONNECTING'
  if (connection !== 'connected') return 'STREAM DISCONNECTED'
  if (!snapshot) return 'AWAITING DATA'
  if (snapshot.feed === 'test') return 'SIMULATED DATA'

  if (
    snapshot.connection_status === 'connected' &&
    snapshot.data_status === 'live' &&
    (snapshot.trade_fresh || snapshot.quote_fresh)
  ) {
    return 'LIVE IEX'
  }

  if (snapshot.data_status === 'stale') return 'STALE DATA'

  return 'AWAITING IEX EVENTS'
}

export function displayPrice(value: string | undefined): string {
  if (!value || !/^\d+(\.\d+)?$/.test(value)) return '—'
  return `$${value}`
}
