import { describe, expect, it } from 'vitest'
import { explainRetainedCash } from './allocationExplanation'
import type { BudgetPlan } from './researchApi'

const base = {
  horizon: 'long', loss_cap_binding: false, experimental_opt_in: false,
  scan_usable_for_ideas: false, quality_review: { applied: false, selected_count: 0 },
  prediction_required: false, historical_comovement_required: false,
  sec_identity_required: false, sec_industry_required: false,
  allocation: [{ category: 'cash' }],
} as BudgetPlan

describe('retained cash explanation', () => {
  it('explains intentional cash when experimental ideas are off', () => {
    const reasons = explainRetainedCash(base).join(' ')
    expect(reasons).toContain('deliberately retains some cash')
    expect(reasons).toContain('Individual-stock research is off')
  })
  it('explains prediction withholding without inventing a forecast', () => {
    const result = explainRetainedCash({
      ...base, experimental_opt_in: true, scan_usable_for_ideas: true,
      quality_review: { ...base.quality_review, applied: true },
      prediction_required: true,
      prediction_review: { status: 'insufficient_evidence' },
    } as BudgetPlan).join(' ')
    expect(result).toContain('Prospective model validation has not passed')
    expect(result).toContain('No experimental candidate survived')
  })
  it('describes the near-term cash and loss-budget constraints', () => {
    const reasons = explainRetainedCash({ ...base, horizon: 'short', loss_cap_binding: true })
    expect(reasons.join(' ')).toContain('short-horizon scenario')
    expect(reasons.join(' ')).toContain('Your affordable-loss limit')
  })
})
