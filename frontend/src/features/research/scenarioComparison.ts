import type { BudgetPlan, InvestmentHorizon, PlanStyle } from './researchApi'

export const COMPARISON_STYLES = ['cautious', 'balanced', 'growth'] as const
export const STYLE_LABELS: Record<PlanStyle, string> = {
  cautious: 'Cautious', balanced: 'Balanced', growth: 'Growth-oriented',
}

export interface ComparisonSettings {
  budget: string
  horizon: InvestmentHorizon
  maxLoss: string
  experimental: boolean
  secIdentity: boolean
  secIndustry: boolean
  prediction: boolean
  comovement: boolean
}

export interface CheckedScenario {
  plan: BudgetPlan
  coreCents: number
  stockCents: number
  cashCents: number
  investedCents: number
  stress30LossCents: number | null
}

export interface CheckedComparison {
  scenarios: CheckedScenario[]
  budgetCents: number
  capturedAtUtc: string
  researchSignature: string | null
}

/** Convert a decimal dollar string into integer cents without floating-point rounding. */
export function centsOf(value: string): number | null {
  if (!/^\d+(?:\.\d{1,2})?$/.test(value)) return null
  const [whole, fraction = ''] = value.split('.')
  const result = Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
  return Number.isSafeInteger(result) ? result : null
}

export function validateComparisonSettings(settings: ComparisonSettings): string | null {
  const budgetCents = centsOf(settings.budget)
  if (budgetCents === null || budgetCents < 1 || budgetCents > 100_000_000) {
    return 'Enter a budget from $0.01 to $1,000,000 using whole cents.'
  }
  const lossCents = settings.maxLoss === '' ? null : centsOf(settings.maxLoss)
  if (settings.maxLoss !== '' && (lossCents === null || lossCents > budgetCents)) {
    return 'The affordable-loss limit must be between $0.00 and the full budget.'
  }
  return null
}

function amount(value: string): number {
  const cents = centsOf(value)
  if (cents === null || cents < 0) throw new Error('One scenario returned an invalid dollar amount.')
  return cents
}

/** Never display or export an arithmetically invalid or mismatched plan as comparable. */
export function checkComparison(
  plans: BudgetPlan[], settings: ComparisonSettings, capturedAtUtc: string,
): CheckedComparison {
  const error = validateComparisonSettings(settings)
  if (error) throw new Error(error)
  if (plans.length !== COMPARISON_STYLES.length) throw new Error('Not all allocation styles returned a result.')
  const budgetCents = amount(settings.budget)
  const lossCents = settings.maxLoss === '' ? null : amount(settings.maxLoss)
  const scenarios: CheckedScenario[] = []
  const signatures: string[] = []
  const secHashes: string[] = []
  const sicHashes: string[] = []
  const predictionHashes: string[] = []

  for (let i = 0; i < plans.length; i += 1) {
    const plan = plans[i]
    if (!plan || plan.style !== COMPARISON_STYLES[i] || plan.horizon !== settings.horizon ||
      amount(plan.budget_usd) !== budgetCents ||
      (plan.max_loss_usd === null ? null : amount(plan.max_loss_usd)) !== lossCents ||
      plan.experimental_opt_in !== settings.experimental) {
      throw new Error('The scenarios do not share the same requested assumptions.')
    }
    if (!Array.isArray(plan.allocation) || plan.allocation.length === 0) {
      throw new Error('A scenario is missing its allocation breakdown.')
    }
    let coreCents = 0
    let stockCents = 0
    let cashCents = 0
    for (const slice of plan.allocation) {
      const sliceCents = amount(slice.amount_usd)
      switch (slice.category) {
        case 'diversified_core_example': coreCents += sliceCents; break
        case 'experimental_stock_idea': stockCents += sliceCents; break
        case 'cash': cashCents += sliceCents; break
        default: throw new Error('An allocation contains an unknown category.')
      }
    }
    const investedCents = amount(plan.total_invested_example_usd)
    if (coreCents + stockCents !== investedCents ||
      cashCents !== amount(plan.unallocated_cash_usd) ||
      investedCents + cashCents !== budgetCents) {
      throw new Error('An allocation does not add up to the investment budget.')
    }
    const stress30 = plan.stress_scenarios.find(row => row.decline_percent === 30)
    const stress30LossCents = stress30 ? amount(stress30.loss_usd) : null
    if (stress30 && (stress30LossCents === null ||
      Math.abs(stress30LossCents + amount(stress30.remaining_budget_usd) - budgetCents) > 1)) {
      throw new Error('A scenario contains inconsistent illustrative stress figures.')
    }
    const signature = JSON.stringify({
      kind: plan.source_kind,
      session: plan.source_session,
      usable: plan.scan_usable_for_ideas,
    })
    signatures.push(signature)
    if (plan.sec_identity_review?.source_sha256) secHashes.push(plan.sec_identity_review.source_sha256)
    if (plan.sec_industry_review?.source_sha256) sicHashes.push(plan.sec_industry_review.source_sha256)
    if (plan.prediction_review?.source_sha256) predictionHashes.push(plan.prediction_review.source_sha256)
    scenarios.push({ plan, coreCents, stockCents, cashCents, investedCents, stress30LossCents })
  }
  // A scanner or saved journal can change while three independent requests are
  // being processed. If so, refuse an apparently apples-to-apples comparison.
  if (settings.experimental && (
    new Set(signatures).size !== 1 || new Set(secHashes).size > 1 ||
    new Set(sicHashes).size > 1 || new Set(predictionHashes).size > 1
  )) {
    throw new Error('Research sources changed while comparing. Run the comparison again.')
  }
  return {
    scenarios, budgetCents, capturedAtUtc,
    researchSignature: settings.experimental ? signatures[0] : null,
  }
}

/** A safe, stable CSV export of the actual API allocations (never predicted returns). */
export function comparisonCsv(checked: CheckedComparison): string {
  const columns = [
    'exported_at_utc', 'style', 'horizon', 'budget_usd', 'max_loss_usd',
    'research_source', 'source_session', 'asset_category', 'symbol', 'name',
    'allocation_usd', 'invested_total_usd', 'retained_cash_usd',
    'illustrative_30pct_loss_usd', 'prediction_required', 'prediction_status',
    'sec_required', 'industry_required', 'historical_comovement_required',
    'historical_comovement_status', 'explanation',
  ]
  function escapeCell(value: unknown): string {
    let text = value === null || value === undefined ? '' : String(value)
    // Prevent ticker, company name, and explanation values from executing as
    // spreadsheet formulas when exported CSV is opened by a spreadsheet app.
    let prefixLength = 0
    while (
      prefixLength < text.length &&
      (text.charCodeAt(prefixLength) < 32 || /\\s/u.test(text[prefixLength]))
    ) {
      prefixLength++
    }
    if (prefixLength < text.length && '=+-@'.includes(text[prefixLength])) {
      text = `'${text}`
    }
    return `"${text.replace(/"/g, '""')}"`
  }
  const rows = [columns.map(escapeCell).join(',')]
  for (const { plan, stress30LossCents } of checked.scenarios) {
    for (const row of plan.allocation) {
      rows.push([
        checked.capturedAtUtc, plan.style, plan.horizon, plan.budget_usd,
        plan.max_loss_usd, plan.source_kind, plan.source_session, row.category,
        row.symbol, row.name, row.amount_usd, plan.total_invested_example_usd,
        plan.unallocated_cash_usd,
        stress30LossCents === null ? null : (stress30LossCents / 100).toFixed(2),
        plan.prediction_required ?? false, plan.prediction_review?.status,
        plan.sec_identity_required ?? false, plan.sec_industry_required ?? false,
        plan.historical_comovement_required ?? false, plan.comovement_review?.status,
        row.reason,
      ].map(escapeCell).join(','))
    }
  }
  return `${rows.join('\r\n')}\r\n`
}

export function plannerDestination(settings: ComparisonSettings, style: PlanStyle): string {
  const query = new URLSearchParams({
    budget: settings.budget, style, horizon: settings.horizon,
  })
  if (settings.maxLoss !== '') query.set('loss', settings.maxLoss)
  if (settings.experimental) query.set('experimental', '1')
  if (settings.experimental && settings.secIdentity) query.set('sec', '1')
  if (settings.experimental && settings.secIndustry) query.set('industry', '1')
  if (settings.experimental && settings.prediction) query.set('prediction', '1')
  if (settings.experimental) query.set('history', settings.comovement ? '1' : '0')
  return `/planner?${query.toString()}`
}

export function readPlannerQuery(query: URLSearchParams): {
  budget: string; style: PlanStyle; horizon: InvestmentHorizon; maxLoss: string;
  experimental: boolean; secIdentity: boolean; secIndustry: boolean;
  prediction: boolean; comovement: boolean
} {
  const candidateBudget = query.get('budget') ?? '100.00'
  const budget = centsOf(candidateBudget) !== null &&
    (centsOf(candidateBudget) ?? 0) >= 1 && (centsOf(candidateBudget) ?? 0) <= 100_000_000
    ? candidateBudget : '100.00'
  const candidateStyle = query.get('style')
  const style: PlanStyle = candidateStyle === 'cautious' || candidateStyle === 'growth'
    ? candidateStyle : 'balanced'
  const candidateHorizon = query.get('horizon')
  const horizon: InvestmentHorizon = candidateHorizon === 'short' || candidateHorizon === 'medium'
    ? candidateHorizon : 'long'
  const candidateLoss = query.get('loss') ?? ''
  const maxLoss = candidateLoss !== '' && centsOf(candidateLoss) !== null &&
    (centsOf(candidateLoss) ?? 0) <= (centsOf(budget) ?? 0) ? candidateLoss : ''
  const experimental = query.get('experimental') === '1'
  const secIndustry = experimental && query.get('industry') === '1'
  return {
    budget, style, horizon, maxLoss, experimental,
    secIdentity: experimental && (query.get('sec') === '1' || secIndustry),
    secIndustry,
    prediction: experimental && query.get('prediction') === '1',
    comovement: !experimental || query.get('history') !== '0',
  }
}
