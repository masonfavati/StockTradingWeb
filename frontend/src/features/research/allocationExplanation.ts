import type { BudgetPlan } from './researchApi'

export function explainRetainedCash(plan: BudgetPlan): string[] {
  const messages: string[] = []
  if (plan.horizon === 'short') {
    messages.push('This short-horizon scenario keeps the full budget in cash rather than exposing near-term funds to stock volatility.')
  } else {
    messages.push('The chosen allocation style deliberately retains some cash; cash is not a predicted return or proof that every stock is unattractive.')
  }
  if (plan.loss_cap_binding) {
    messages.push('Your affordable-loss limit reduced the amount exposed to risky assets. It does not guarantee that losses will stay below that limit.')
  }
  if (!plan.experimental_opt_in) {
    messages.push('Individual-stock research is off. No experimental stock budget is allocated without your opt-in.')
    return messages
  }
  if (!plan.scan_usable_for_ideas) {
    messages.push('No qualifying recent scanner snapshot was used, so individual-stock dollars cannot be allocated from older or missing research.')
  }
  if (plan.quality_review?.applied && plan.quality_review.selected_count === 0) {
    messages.push('No experimental candidate survived the enabled screening steps.')
  }
  if (plan.prediction_required && plan.prediction_review?.status !== 'research_gate_passed') {
    messages.push('Prospective model validation has not passed. Prediction-dependent experimental dollars remain cash.')
  }
  if (plan.sec_identity_required && plan.sec_identity_review?.status !== 'checked') {
    messages.push('SEC filing-entity evidence is missing, stale, or unavailable for some proposed stocks.')
  }
  if (plan.sec_industry_required && plan.sec_industry_review?.status !== 'checked') {
    messages.push('SEC industry evidence is missing, stale, or not linked to the current filer reference.')
  }
  if (plan.historical_comovement_required && plan.comovement_review?.status !== 'checked') {
    messages.push('Historical co-movement evidence was insufficient or unavailable for any proposed stock positions.')
  }
  if (!plan.allocation.some(row => row.category === 'experimental_stock_idea')) {
    messages.push('There are no individual-stock allocations in this example; see the evidence panels above for exclusions and concentration checks.')
  }
  return messages
}
