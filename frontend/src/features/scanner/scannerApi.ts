export interface ResearchCandidate {
  symbol: string
  name: string
  last_session: string
  adjusted_close: number
  return_20d_pct: number
  return_60d_pct: number
  annualized_volatility_pct: number
  drawdown_60d_pct: number
  approx_daily_dollar_volume: number
  research_score: number
}

export interface ScannerStatus {
  state: 'idle' | 'running' | 'complete' | 'failed'
  message: string
  started_at: string | null
  completed_at: string | null
  latest_session: string | null
  directory_size: number
  considered: number
  processed: number
  qualified: number
  candidates: ResearchCandidate[]
}

async function requestScan(url: string, init?: RequestInit): Promise<ScannerStatus> {
  const response = await fetch(url, init)
  if (!response.ok) {
    throw new Error(`Couldn't reach the market scanner (HTTP ${response.status}).`)
  }
  return (await response.json()) as ScannerStatus
}

export function getScannerStatus(): Promise<ScannerStatus> {
  return requestScan('/api/scanner/status')
}

export function startScanner(): Promise<ScannerStatus> {
  return requestScan('/api/scanner/scan', { method: 'POST' })
}
