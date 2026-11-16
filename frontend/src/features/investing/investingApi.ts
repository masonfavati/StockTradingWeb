export type PlanStyle = 'cautious' | 'balanced' | 'growth'
export type HoldingPeriod = 'short' | 'medium' | 'long'
export interface BacktestResult {
  disjoint_test_windows: number
  model_average_error_pp: number | null
  baseline_average_error_pp: number | null
  direction_correct_pct: number | null
  beats_average_baseline: boolean
}
export interface GrowthIdea {
  symbol: string
  estimated_change_pct: number
  historical_analogue_low_pct: number
  historical_analogue_high_pct: number
  current_adjusted_price: number
  estimated_end_price_usd: number
  analogue_low_price_usd: number
  analogue_high_price_usd: number
  as_of: string
  status: 'backtest_candidate' | 'unvalidated'
  backtest: BacktestResult
  history_sessions: number
  similar_past_patterns_with_gain_pct?: number
}
export interface AllocationItem {
  symbol: string | null
  category: 'diversified_core' | 'experimental_stock' | 'cash'
  amount_usd: string
  percent_of_budget: number
  why: string
  estimated_change_pct?: number
  analogue_low_pct?: number
  analogue_high_pct?: number
}
export interface PortfolioApproach {
  id: 'combined' | 'core_only' | 'max_model_change'
  label: string
  available: boolean
  invested_usd: string
  cash_usd: string
  stock_positions: number
  allocation: AllocationItem[]
  illustrative_model_gain_usd: string | null
  past_window_range: {
    windows_compared: number
    worst_observed_change_pct: number
    best_observed_change_pct: number
  } | null
  explanation: string
  winning_structure?: 'spy_and_stocks' | 'stocks_and_cash' | 'spy_only' | 'cash_only' | null
  combinations_considered?: number | null
}
export interface PortfolioComparison {
  forecast_period: string
  forecast_horizon_sessions: number
  approaches: PortfolioApproach[]
  method_warning: string
}
export interface GrowthPlanResponse {
  version: string
  scenario_comparison?: PortfolioComparison
  plan: {
    budget_usd: string
    invested_usd: string
    cash_usd: string
    horizon: HoldingPeriod
    forecast_period: string
    forecast_horizon_sessions: number
    current_model_status: string
    combination_analysis?: {
      method: string
      forecasted_stocks_reviewed: number
      positive_estimate_stocks: number
      risk_eligible_stocks: number
      combinations_considered: number
      stock_positions_selected: number
      illustrative_model_gain_usd: string
    }
    exploratory: boolean
    allocation: AllocationItem[]
    declined: {symbol: string; reason: string}[]
    warning: string
  }
  selection: {source: string; session: string; note?: string}
  ranking_scope?: {
    complete_market_forecast: boolean
    market_symbols_screened: number | null
    preliminary_candidates_quality_screened: number | null
    symbols_selected_for_forecast: number
    symbols_with_estimates: number
  }
  ranked_stocks: GrowthIdea[]
  benchmark: {symbol: string; horizon: string; estimated_change_pct: number}
  preview_history: Record<string, {date: string; adjusted_close: number}[]>
  history_source: string
  evidence_grade: string
  important: string
}
export interface GrowthPlanInput {
  budget_usd: string
  style: PlanStyle
  horizon: HoldingPeriod
  max_loss_usd: string | null
  allow_exploratory: boolean
  symbols: string[]
}
export interface Holding {
  symbol: string
  shares: string
  cost_basis_usd: string
  last_completed_close_usd: string | null
  last_price_date: string | null
  estimated_value_usd: string | null
  unrealized_gain_usd: string | null
  unrealized_gain_pct: number | null
}
export interface ManualTrade {
  id: string
  symbol: string
  action: 'buy' | 'sell' | 'split'
  date: string
  shares?: string
  price_usd?: string
  fee_usd?: string
  ratio?: string
}
export interface PortfolioSummary {
  holdings: Holding[]
  recorded_trades: number
  realized_gain_usd: string
  estimated_portfolio_value_usd: string | null
  valuation_complete: boolean
  caveat: string
}
export interface PortfolioResponse {
  summary: PortfolioSummary
  trades: ManualTrade[]
}
export interface ReviewAlert {
  symbol: string
  status: 'review_exit_rules' | 'no_rule_triggered' | 'data_unavailable'
  observed_drop_pct: number | null
  reasons: string[]
}
export interface PortfolioRefreshResponse {
  summary: PortfolioSummary
  alerts: ReviewAlert[]
  quotes_source: string | null
  alert_explanation?: string
}
async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, init)
  const data: unknown = await response.json().catch(() => null)
  if (!response.ok) {
    const detail = data && typeof data === 'object' && 'detail' in data ? String(data.detail) : 'Request failed.'
    const error = new Error(detail) as Error & { status: number }
    error.status = response.status
    throw error
  }
  return data as T
}
export function getGrowthPlan(input: GrowthPlanInput): Promise<GrowthPlanResponse> {
  return request('/api/investing/plan', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(input),
  })
}
export async function startMarketScan(): Promise<void> {
  await request('/api/scanner/scan', {method: 'POST'})
}
export interface ScannerProgress {
  state: 'idle' | 'running' | 'complete' | 'failed'
  message: string
  processed: number
  considered: number
}
export function getScannerProgress(): Promise<ScannerProgress> {
  return request('/api/scanner/status')
}
export function getPortfolio(): Promise<PortfolioResponse> {return request('/api/investing/portfolio')}
export function refreshPortfolio(): Promise<PortfolioRefreshResponse> {
  return request('/api/investing/portfolio/refresh', {method: 'POST'})
}
export function addPortfolioTrade(input: Omit<ManualTrade, 'id'>): Promise<{saved: boolean}> {
  return request('/api/investing/portfolio/trades', {
    method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify(input),
  })
}
export function undoPortfolioTrade(id: string): Promise<{removed: boolean}> {
  return request(`/api/investing/portfolio/trades/${encodeURIComponent(id)}`, {method: 'DELETE'})
}
