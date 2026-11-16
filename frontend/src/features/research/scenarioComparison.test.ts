import { describe, expect, it } from 'vitest'
import type { BudgetPlan, PlanStyle } from './researchApi'
import {
  centsOf, checkComparison, comparisonCsv, plannerDestination,
  readPlannerQuery, validateComparisonSettings,
  type ComparisonSettings,
} from './scenarioComparison'

const defaults: ComparisonSettings = {
  budget: '100.00', horizon: 'long', maxLoss: '', experimental: false,
  secIdentity: true, secIndustry: true, prediction: true, comovement: true,
}

function sample(style: PlanStyle, overrides: Partial<BudgetPlan> = {}): BudgetPlan {
  const invested = style === 'cautious' ? 60 : style === 'balanced' ? 65 : 70
  const cash = 100 - invested
  return {
    budget_usd: '100.00', style, horizon: 'long', max_loss_usd: null,
    experimental_opt_in: false, modeled_risky_principal_usd: `${invested}.00`,
    loss_cap_binding: false, planning_explanations: [], warnings: [],
    stress_scenarios: [{ decline_percent: 30,
      loss_usd: (invested * 0.3).toFixed(2),
      remaining_budget_usd: (100 - invested * 0.3).toFixed(2) }],
    scan_usable_for_ideas: false, source_session: null, source_kind: null,
    allocation: [
      { category: 'diversified_core_example', symbol: 'SPY', name: 'Core example',
        amount_usd: `${invested}.00`, percent_of_budget: invested,
        indicative_fractional_shares: null, historical_price_usd: null, reason: 'Example' },
      { category: 'cash', symbol: null, name: 'Cash', amount_usd: `${cash}.00`,
        percent_of_budget: cash, indicative_fractional_shares: null,
        historical_price_usd: null, reason: 'Kept uninvested' },
    ],
    total_invested_example_usd: `${invested}.00`, unallocated_cash_usd: `${cash}.00`,
    illustrative_equity_drop_30pct_usd: (invested * 0.3).toFixed(2),
    quality_review: { version: '1', applied: false, screened_count: 0, selected_count: 0,
      excluded_counts: {}, thresholds: { min_adjusted_close_usd: 5,
        min_approx_daily_dollar_volume_usd: 5_000_000,
        max_annualized_volatility_pct: 80,
        min_60d_drawdown_pct: -25, max_individual_stocks: 2 }, caveat: 'No shares recommended' },
    ...overrides,
  }
}

const plans = () => [sample('cautious'), sample('balanced'), sample('growth')]

describe('budget comparison arithmetic and safety', () => {
  it('parses cents strictly and never rounds fractional cents', () => {
    expect(centsOf('12.3')).toBe(1230)
    expect(centsOf('0.01')).toBe(1)
    expect(centsOf('1.001')).toBeNull()
    expect(centsOf('-10')).toBeNull()
    expect(centsOf('1e3')).toBeNull()
  })
  it('validates the budget and affordable-loss limit before making requests', () => {
    expect(validateComparisonSettings(defaults)).toBeNull()
    expect(validateComparisonSettings({ ...defaults, budget: '0' })).toMatch(/budget/)
    expect(validateComparisonSettings({ ...defaults, budget: '100.001' })).toMatch(/budget/)
    expect(validateComparisonSettings({ ...defaults, maxLoss: '100.01' })).toMatch(/affordable-loss/)
    expect(validateComparisonSettings({ ...defaults, maxLoss: '0.00' })).toBeNull()
  })
  it('compares the correct three styles with exact allocation totals', () => {
    const checked = checkComparison(plans(), defaults, '2026-11-16T00:00:00Z')
    expect(checked.budgetCents).toBe(10_000)
    expect(checked.scenarios.map(s => s.investedCents)).toEqual([6000, 6500, 7000])
    expect(checked.scenarios.map(s => s.cashCents)).toEqual([4000, 3500, 3000])
    expect(checked.scenarios[1].stress30LossCents).toBe(1950)
  })
  it('rejects mismatched server totals instead of rendering fake comparisons', () => {
    const bad = plans()
    bad[1] = sample('balanced', { unallocated_cash_usd: '34.99' })
    expect(() => checkComparison(bad, defaults, 'now')).toThrow(/does not add up/)
  })
  it('rejects wrong style, horizon, budget and loss cap', () => {
    const bad = plans()
    bad[1] = sample('growth')
    expect(() => checkComparison(bad, defaults, 'now')).toThrow(/same requested assumptions/)
    expect(() => checkComparison(plans(), { ...defaults, maxLoss: '20' }, 'now'))
      .toThrow(/same requested assumptions/)
  })
  it('allows a one-cent stress rounding difference but never an allocation mismatch', () => {
    const minor = plans()
    minor[2] = sample('growth', { stress_scenarios: [{
      decline_percent: 30, loss_usd: '21.00', remaining_budget_usd: '79.01',
    }] })
    expect(checkComparison(minor, defaults, 'now').scenarios[2].stress30LossCents).toBe(2100)
  })
  it('rejects incomplete or inconsistent stress scenarios', () => {
    const bad = plans()
    bad[2] = sample('growth', { stress_scenarios: [{
      decline_percent: 30, loss_usd: '21.00', remaining_budget_usd: '80.00',
    }] })
    expect(() => checkComparison(bad, defaults, 'now')).toThrow(/stress/)
  })
  it('refuses to compare experimental scenarios from different source sessions', () => {
    const bad = plans().map(plan => ({ ...plan, experimental_opt_in: true,
      source_kind: 'frozen_checkpoint' as const, source_session: '2026-11-13',
    }))
    bad[2].source_session = '2026-11-14'
    expect(() => checkComparison(bad, { ...defaults, experimental: true }, 'now'))
      .toThrow(/Research sources changed/)
  })
  it('escapes spreadsheet formulas and quotes in exported metadata', () => {
    const bad = plans()
    bad[0].allocation[0].name = '=WEBSERVICE("example")'
    const checked = checkComparison(bad, defaults, '2026-11-16T00:00:00Z')
    const csv = comparisonCsv(checked)
    expect(csv).toContain('"\'=WEBSERVICE(""example"")"')
    expect(csv).toContain('"cautious"')
    expect(csv).toContain('"65.00"')
    expect(csv.split('\r\n').filter(Boolean)).toHaveLength(7)
  })
  it('prefills the full planner without triggering purchases or automatic queries', () => {
    const selections: ComparisonSettings = {
      ...defaults, budget: '250.50', horizon: 'medium', maxLoss: '40.00',
      experimental: true, comovement: false,
    }
    const link = plannerDestination(selections, 'growth')
    expect(link).toContain('/planner?')
    const parsed = readPlannerQuery(new URLSearchParams(link.split('?')[1]))
    expect(parsed).toMatchObject({
      budget: '250.50', horizon: 'medium', style: 'growth', maxLoss: '40.00',
      experimental: true, prediction: true, secIdentity: true, secIndustry: true,
      comovement: false,
    })
  })
  it('ignores malformed or unreasonable planner query parameters', () => {
    const parsed = readPlannerQuery(new URLSearchParams(
      'budget=999999999999&style=unsupported&horizon=forever&loss=1000000&experimental=yes',
    ))
    expect(parsed).toMatchObject({
      budget: '100.00', style: 'balanced', horizon: 'long', maxLoss: '', experimental: false,
    })
  })
})
