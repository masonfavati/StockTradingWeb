export type HistoryPeriod = '1m' | '3m' | '1y' | '5y'

export interface HistoryBar {
  session_date: string
  adjusted_close_usd: number
  normalized_index: number
}
export interface BenchmarkBar {
  session_date: string
  normalized_index: number
}
export interface StockHistoryResponse {
  version: string
  symbol: string
  period: HistoryPeriod
  provider: 'alpaca'
  feed: 'sip'
  adjustment: 'all'
  timeframe: '1Day'
  fetched_at_utc: string
  provider_cutoff_utc: string
  first_session: string | null
  last_session: string | null
  session_count: number
  first_adjusted_close_usd: number | null
  last_adjusted_close_usd: number | null
  period_change_pct: number | null
  benchmark_requested: boolean
  benchmark_available: boolean
  benchmark_anchor_session: string | null
  bars: HistoryBar[]
  spy_benchmark: BenchmarkBar[]
  warning: string | null
  price_forecast: null
  forecast_status: 'no_validated_price_forecast'
  forecast_explanation: string
  caveat: string
}

export const validHistoryTicker = (value: string): boolean =>
  /^[A-Z][A-Z0-9.-]{0,19}$/.test(value.trim().toUpperCase())

export function historyLink(symbol: string, signal?: string | null): string {
  const args = new URLSearchParams({ symbol: symbol.toUpperCase() })
  if (signal && /^\d{4}-\d{2}-\d{2}$/.test(signal)) args.set('signal', signal)
  return `/history?${args.toString()}`
}

export async function getStockHistory(
  symbol: string, period: HistoryPeriod, compareSpy: boolean,
  signal?: AbortSignal,
): Promise<StockHistoryResponse> {
  if (!validHistoryTicker(symbol)) throw new Error('Enter a valid stock ticker.')
  const args = new URLSearchParams({ period, compare_spy: String(compareSpy) })
  const response = await fetch(`/api/research/stock-history/${encodeURIComponent(symbol.trim().toUpperCase())}?${args}`, { signal })
  if (!response.ok) {
    if (response.status === 429) throw new Error('Too many chart requests. Please retry in a minute.')
    throw new Error('Historical prices could not be retrieved. Check Alpaca access or try again.')
  }
  return await response.json() as StockHistoryResponse
}
