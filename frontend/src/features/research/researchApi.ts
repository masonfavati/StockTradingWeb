export interface OutcomeGroup {
  research_rule: string
  holding_sessions: number
  registered_checkpoints: number
  status_counts: Record<string, number>
  metrics: null | {
    complete_windows: number
    mean_selected_net_pct: string
    mean_spy_net_pct: string
    mean_paired_excess_pp: string
    positive_selected_windows: number
    windows_beating_spy: number
  }
  overlap: {
    overlapping_pairs: number
    maximum_date_disjoint_windows: number
  }
}

export interface FrozenResearchSummary {
  signal_session: string
  recorded_at_utc: string
  eligible_symbols_considered: number
  qualified_by_scanner: number
  candidates: { symbol: string; name: string; return_60d_pct: number }[]
}

export interface ResearchOverviewResponse {
  latest_checkpoint: FrozenResearchSummary | null
  generated_at_utc: string
  registered_checkpoints: number
  status_counts: Record<string, number>
  groups: OutcomeGroup[]
  warnings: string[]
}

export type PlanStyle = 'cautious' | 'balanced' | 'growth'
export type InvestmentHorizon = 'short' | 'medium' | 'long'
export interface BudgetSlice {
  category: 'diversified_core_example' | 'experimental_stock_idea' | 'cash'
  symbol: string | null
  name: string
  amount_usd: string
  percent_of_budget: number
  indicative_fractional_shares: string | null
  historical_price_usd: string | null
  reason: string
}
export interface QualityReview {
  version: string
  applied: boolean
  screened_count: number
  selected_count: number
  excluded_counts: Record<string, number>
  thresholds: {
    min_adjusted_close_usd: number
    min_approx_daily_dollar_volume_usd: number
    max_annualized_volatility_pct: number
    min_60d_drawdown_pct: number
    max_individual_stocks: number
  }
  caveat: string
}

export interface ComovementReview {
  version: string
  status: 'checked' | 'insufficient_history' | 'unavailable' | 'not_applicable'
  requested_symbols: string[]
  approved_symbols: string[]
  excluded: { symbol: string; reason: string }[]
  matched_sessions: number
  pairwise_correlations: { symbol_a: string; symbol_b: string; correlation: number; paired_returns: number }[]
  spy_correlations: { symbol: string; correlation: number; paired_returns: number }[]
  portfolio_annualized_historical_volatility_pct: number | null
  portfolio_historical_max_drawdown_pct: number | null
  threshold_positive_correlation: number
  caveat: string
}

export interface BudgetPlan {
  historical_comovement_required?: boolean
  comovement_review?: ComovementReview | null
  budget_usd: string
  style: PlanStyle
  horizon: InvestmentHorizon
  max_loss_usd: string | null
  modeled_risky_principal_usd: string
  loss_cap_binding: boolean
  planning_explanations: string[]
  stress_scenarios: { decline_percent: number; loss_usd: string; remaining_budget_usd: string }[]
  experimental_opt_in: boolean
  quality_review: QualityReview
  scan_usable_for_ideas: boolean
  source_session: string | null
  source_kind: 'website_scan' | 'frozen_checkpoint' | null
  allocation: BudgetSlice[]
  total_invested_example_usd: string
  unallocated_cash_usd: string
  illustrative_equity_drop_30pct_usd: string
  warnings: string[]
}

export async function getResearchOverview(): Promise<ResearchOverviewResponse> {
  const response = await fetch('/api/research/overview')
  if (!response.ok) throw new Error('The verified research journal is unavailable.')
  return (await response.json()) as ResearchOverviewResponse
}

export async function calculateBudgetPlan(
  budget: string, style: PlanStyle, experimental: boolean,
  horizon: InvestmentHorizon = 'long', maxLoss: string | null = null,
  requireHistoricalComovement = false,
): Promise<BudgetPlan> {
  const response = await fetch('/api/research/budget-plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      budget_usd: budget,
      style,
      allow_experimental_stocks: experimental,
      horizon,
      max_loss_usd: maxLoss,
      ...(requireHistoricalComovement ? { require_historical_comovement: true } : {}),
    }),
  })
  if (!response.ok) throw new Error('Could not calculate the budget scenario. Check your amount and try again.')
  return (await response.json()) as BudgetPlan
}
