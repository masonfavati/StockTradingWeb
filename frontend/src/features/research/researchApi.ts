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
export interface BudgetPlan {
  budget_usd: string
  style: PlanStyle
  experimental_opt_in: boolean
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
): Promise<BudgetPlan> {
  const response = await fetch('/api/research/budget-plan', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      budget_usd: budget,
      style,
      allow_experimental_stocks: experimental,
    }),
  })
  if (!response.ok) throw new Error('Could not calculate the budget scenario. Check your amount and try again.')
  return (await response.json()) as BudgetPlan
}
