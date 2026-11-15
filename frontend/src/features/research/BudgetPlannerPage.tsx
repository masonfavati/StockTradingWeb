import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import {
  calculateBudgetPlan,
  type BudgetPlan,
  type InvestmentHorizon,
  type PlanStyle,
} from './researchApi'

const qualityLabels: Record<string, string> = {
  unverified_share_type: 'Not enough evidence of ordinary shares',
  duplicate_ticker: 'Duplicate ticker',
  outdated_session: 'Not from the latest completed session',
  missing_or_invalid_metrics: 'Missing or invalid historical risk/liquidity data',
  below_price_floor: 'Below historical adjusted-price threshold',
  below_liquidity_screen: 'Below approximate historical trading-volume threshold',
  above_volatility_screen: 'Volatility exceeds research threshold',
  outside_drawdown_screen: 'Recent drawdown outside research threshold',
  repeated_apparent_issuer: 'Possible duplicate company/share class',
  passed_not_selected: 'Passed screens; excluded by two-stock concentration limit',
}

function dollars(value: string): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))
}

export default function BudgetPlannerPage() {
  const [budget, setBudget] = useState('100.00')
  const [style, setStyle] = useState<PlanStyle>('balanced')
  const [horizon, setHorizon] = useState<InvestmentHorizon>('long')
  const [maxLoss, setMaxLoss] = useState('')
  const [experimental, setExperimental] = useState(false)
  const [plan, setPlan] = useState<BudgetPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const requestSerial = useRef(0)

  function invalidatePlan() {
    requestSerial.current += 1
    setPlan(null)
    setError(null)
    setPending(false)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const serial = ++requestSerial.current
    setError(null)
    setPlan(null)
    if (!/^\d+(\.\d{1,2})?$/.test(budget) || Number(budget) <= 0 || Number(budget) > 1_000_000) {
      setError('Enter an amount from $0.01 to $1,000,000, using at most two decimal places.')
      return
    }
    if (maxLoss !== '' && (!/^\d+(\.\d{1,2})?$/.test(maxLoss) || Number(maxLoss) > Number(budget))) {
      setError('The maximum affordable loss must be between $0.00 and your investment amount, in whole cents.')
      return
    }
    setPending(true)
    try {
      const calculated = await calculateBudgetPlan(budget, style, experimental, horizon, maxLoss || null)
      if (requestSerial.current === serial) setPlan(calculated)
    } catch (caught) {
      if (requestSerial.current === serial) {
        setError(caught instanceof Error ? caught.message : 'Unable to calculate a plan.')
      }
    } finally {
      if (requestSerial.current === serial) setPending(false)
    }
  }

  return <section className="space-y-6" aria-label="Investment budget planner">
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-8">
      <p className="text-sm font-semibold text-emerald-400">Research and plan</p>
      <h1 className="mt-2 text-3xl font-bold">Investment Budget Planner</h1>
      <p className="mt-3 max-w-3xl text-slate-300">
        Choose a dollar amount, investment time horizon, and optional affordable-loss limit.
        See a transparent example of where those dollars would go, plus downside scenarios.
      </p>
      <p className="mt-3 text-sm text-amber-200">
        Educational scenarios only—not an optimized portfolio or personalized buy advice.
        The scanner's future-return accuracy has not been validated.
      </p>
    </div>

    <form className="grid gap-5 rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:grid-cols-2" onSubmit={(e) => { void submit(e) }}>
      <div>
        <label htmlFor="investment-budget" className="block text-sm font-medium">Amount you intend to invest</label>
        <div className="mt-2 flex items-center rounded-lg border border-slate-700 bg-slate-950 px-3">
          <span className="text-slate-400">$</span>
          <input id="investment-budget" aria-label="Investment amount in dollars" value={budget}
            onChange={(event) => { setBudget(event.target.value); invalidatePlan() }} inputMode="decimal"
            className="w-full bg-transparent px-2 py-3 text-white outline-none" placeholder="100.00" />
        </div>
      </div>
      <div>
        <label htmlFor="investment-style" className="block text-sm font-medium">Illustrative allocation style</label>
        <select id="investment-style" value={style} onChange={(event) => { setStyle(event.target.value as PlanStyle); invalidatePlan() }}
          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white">
          <option value="cautious">Cautious — less stock exposure</option>
          <option value="balanced">Balanced — diversified core</option>
          <option value="growth">Growth-oriented — more stock exposure</option>
        </select>
      </div>
      <div>
        <label htmlFor="investment-horizon" className="block text-sm font-medium">When might you need this money?</label>
        <select id="investment-horizon" value={horizon} onChange={(event) => { setHorizon(event.target.value as InvestmentHorizon); invalidatePlan() }}
          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white">
          <option value="short">Within 1 year</option>
          <option value="medium">In 1–5 years</option>
          <option value="long">In 5+ years (example default)</option>
        </select>
        <p className="mt-2 text-xs text-slate-400">A shorter time horizon reduces the example's equity exposure.</p>
      </div>
      <div>
        <label htmlFor="maximum-loss" className="block text-sm font-medium">Maximum you could afford to lose (optional)</label>
        <div className="mt-2 flex items-center rounded-lg border border-slate-700 bg-slate-950 px-3">
          <span className="text-slate-400">$</span>
          <input id="maximum-loss" aria-label="Maximum affordable loss in dollars" value={maxLoss}
            onChange={(event) => { setMaxLoss(event.target.value); invalidatePlan() }} inputMode="decimal"
            className="w-full bg-transparent px-2 py-3 text-white outline-none" placeholder="e.g. 25.00" />
        </div>
        <p className="mt-2 text-xs text-slate-400">
          If entered, the example puts no more than this amount into risky assets. This is a spending cap, not a predicted loss.
        </p>
      </div>
      <label className="flex items-start gap-3 text-sm text-slate-200 sm:col-span-2">
        <input type="checkbox" className="mt-1 accent-emerald-500" checked={experimental}
          onChange={(event) => { setExperimental(event.target.checked); invalidatePlan() }} />
        <span>Include experimental individual-stock ideas from a recent completed scanner run.
          Each stock is limited to 10% of the budget. These are not verified common shares or buy recommendations.</span>
      </label>
      <div className="sm:col-span-2">
        <button type="submit" disabled={pending}
          className="rounded-lg bg-emerald-600 px-5 py-3 font-semibold text-white hover:bg-emerald-500 disabled:opacity-50">
          {pending ? 'Calculating…' : 'Show budget example'}
        </button>
      </div>
    </form>

    {error && <p role="alert" className="rounded-lg border border-red-900 p-4 text-red-300">{error}</p>}
    {plan && <div className="space-y-5" role="region" aria-label="Illustrative budget allocation">
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-2xl font-semibold">Illustrative split for {dollars(plan.budget_usd)}</h2>
        <p className="mt-2 text-sm text-slate-400">
          {plan.source_session ? `Research prices through ${plan.source_session} (${plan.source_kind === 'frozen_checkpoint' ? 'frozen journal' : 'website scan'}). ` :
            'No fresh individual-stock shortlist is used for this scenario. '}
          No orders are placed.
        </p>
        <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950 p-4">
          <h3 className="font-semibold">Why these amounts?</h3>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-slate-300">
            {plan.planning_explanations.map((explanation) => <li key={explanation}>{explanation}</li>)}
          </ul>
          <p className="mt-3 text-sm text-amber-200">
            Risk-bearing amount: {dollars(plan.modeled_risky_principal_usd)}.
            {plan.max_loss_usd !== null
              ? ` You entered ${dollars(plan.max_loss_usd)} as the most you could afford to lose.`
              : ' No personal affordable-loss cap was provided.'}
          </p>
          {plan.loss_cap_binding && <p className="mt-2 text-sm text-emerald-300">
            The dollar-loss limit reduced this scenario's stock exposure.
          </p>}
        </div>
        {plan.experimental_opt_in && <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950 p-4">
          <h3 className="font-semibold">Individual-stock research quality checks</h3>
          {plan.quality_review?.applied ? <>
            <p className="mt-2 text-sm text-slate-300">
              Reviewed {plan.quality_review.screened_count} ranked shortlist candidates; selected{' '}
              {plan.quality_review.selected_count} for possible experimental slices.
              This is not a review of every security in the market.
            </p>
            <p className="mt-2 text-xs text-slate-400">
              Historical adjusted price ≥ {dollars(String(plan.quality_review.thresholds.min_adjusted_close_usd))};
              {' '}approximate recent daily dollar volume ≥ {dollars(String(plan.quality_review.thresholds.min_approx_daily_dollar_volume_usd))};
              {' '}annualized volatility ≤ {plan.quality_review.thresholds.max_annualized_volatility_pct}%;
              {' '}60-session drawdown ≥ {plan.quality_review.thresholds.min_60d_drawdown_pct}%.
              At most {plan.quality_review.thresholds.max_individual_stocks} apparent distinct issuers.
            </p>
            {Object.entries(plan.quality_review.excluded_counts).length > 0 && <div className="mt-3">
              <p className="text-sm font-semibold">Why shortlist candidates were excluded</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-300">
                {Object.entries(plan.quality_review.excluded_counts).map(([key, count]) =>
                  <li key={key}>{qualityLabels[key] ?? key}: {count}</li>)}
              </ul>
            </div>}
            <p className="mt-3 text-xs text-amber-200">{plan.quality_review.caveat}</p>
          </> : <p className="mt-2 text-sm text-amber-200">
            No quality screening was applied because the optional stock allocation was not available,
            the historical shortlist was not recent enough, or the risk budget was too small.
          </p>}
        </div>}
        <div className="mt-5 space-y-3">
          {plan.allocation.map((item, index) => (
            <article key={`${item.symbol ?? 'cash'}-${index}`} className="rounded-xl border border-slate-700 bg-slate-950 p-4">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div>
                  <h3 className="font-semibold">{item.name}</h3>
                  <p className="text-xs text-slate-400">{item.symbol ? `Ticker: ${item.symbol} · ` : ''}{item.reason}</p>
                </div>
                <div className="text-right">
                  <p className="text-xl font-semibold">{dollars(item.amount_usd)}</p>
                  <p className="text-xs text-slate-400">{item.percent_of_budget}% of budget</p>
                </div>
              </div>
              {item.indicative_fractional_shares !== null && <p className="mt-2 text-xs text-amber-200">
                Approximately {item.indicative_fractional_shares} fractional shares using an old adjusted close
                of {dollars(item.historical_price_usd ?? '0')}; not a current executable quote.
              </p>}
            </article>
          ))}
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-700 pt-4 text-sm">
          <div><dt className="text-slate-400">Example invested amount</dt>
            <dd className="mt-1 text-xl font-bold">{dollars(plan.total_invested_example_usd)}</dd></div>
          <div><dt className="text-slate-400">Retained as cash</dt>
            <dd className="mt-1 text-xl font-bold">{dollars(plan.unallocated_cash_usd)}</dd></div>
        </dl>
      </div>
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-xl font-semibold">Hypothetical downside scenarios</h2>
        <p className="mt-2 text-sm text-slate-400">
          These are simple percentage declines applied to the invested amount, not return forecasts or risk estimates.
          Cash is held constant for illustration only.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {plan.stress_scenarios.map((scenario) => <div key={scenario.decline_percent}
            className="rounded-xl border border-slate-700 bg-slate-950 p-4">
            <p className="text-sm text-slate-400">Risky assets fall {scenario.decline_percent}%</p>
            <p className="mt-2 text-xl font-semibold text-amber-200">−{dollars(scenario.loss_usd)}</p>
            <p className="mt-1 text-xs text-slate-400">Budget remaining: {dollars(scenario.remaining_budget_usd)}</p>
          </div>)}
        </div>
      </div>
      <div className="rounded-xl border border-slate-800 p-5">
        <h2 className="text-lg font-semibold">Before investing real money</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-400">
          {plan.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
        <Link className="mt-4 inline-block text-emerald-400 hover:underline" to="/scanner">
          Review the underlying research shortlist
        </Link>
      </div>
    </div>}
  </section>
}
