import { useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { calculateBudgetPlan, type BudgetPlan, type PlanStyle } from './researchApi'

function dollars(value: string): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))
}

export default function BudgetPlannerPage() {
  const [budget, setBudget] = useState('100.00')
  const [style, setStyle] = useState<PlanStyle>('balanced')
  const [experimental, setExperimental] = useState(false)
  const [plan, setPlan] = useState<BudgetPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(null)
    setPlan(null)
    if (!/^\d+(\.\d{1,2})?$/.test(budget) || Number(budget) <= 0 || Number(budget) > 1_000_000) {
      setError('Enter an amount from $0.01 to $1,000,000, using at most two decimal places.')
      return
    }
    setPending(true)
    try {
      setPlan(await calculateBudgetPlan(budget, style, experimental))
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : 'Unable to calculate a plan.')
    } finally {
      setPending(false)
    }
  }

  return <section className="space-y-6" aria-label="Investment budget planner">
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-8">
      <p className="text-sm font-semibold text-emerald-400">Research and plan</p>
      <h1 className="mt-2 text-3xl font-bold">Investment Budget Planner</h1>
      <p className="mt-3 max-w-3xl text-slate-300">
        Tell us how much you're considering investing. See a dollar-by-dollar example split between
        a diversified market fund, optional experimental stocks, and cash.
      </p>
      <p className="mt-3 text-sm text-amber-200">
        Educational example only—not advice that these are the best investments for you.
        Our stock scanner has not established reliable predictive performance.
      </p>
    </div>

    <form className="grid gap-5 rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:grid-cols-2" onSubmit={(e) => { void submit(e) }}>
      <div>
        <label htmlFor="investment-budget" className="block text-sm font-medium">How much are you considering?</label>
        <div className="mt-2 flex items-center rounded-lg border border-slate-700 bg-slate-950 px-3">
          <span className="text-slate-400">$</span>
          <input id="investment-budget" aria-label="Investment amount in dollars" value={budget}
            onChange={(event) => setBudget(event.target.value)} inputMode="decimal"
            className="w-full bg-transparent px-2 py-3 text-white outline-none" placeholder="100.00" />
        </div>
      </div>
      <div>
        <label htmlFor="investment-style" className="block text-sm font-medium">Example allocation style</label>
        <select id="investment-style" value={style} onChange={(event) => setStyle(event.target.value as PlanStyle)}
          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white">
          <option value="cautious">Cautious — more cash</option>
          <option value="balanced">Balanced — diversified core</option>
          <option value="growth">Growth-oriented — more invested</option>
        </select>
      </div>
      <label className="flex items-start gap-3 text-sm text-slate-200 sm:col-span-2">
        <input type="checkbox" className="mt-1 accent-emerald-500" checked={experimental}
          onChange={(event) => setExperimental(event.target.checked)} />
        <span>Include experimental individual-stock ideas from a fresh completed scanner run.
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
            'No fresh, verified-type stock shortlist is available for this scenario. '}
          No orders are placed.
        </p>
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
          <div className="col-span-2"><dt className="text-slate-400">What if the invested portion fell 30%?</dt>
            <dd className="mt-1 text-lg font-semibold text-amber-200">Approx. {dollars(plan.illustrative_equity_drop_30pct_usd)} loss</dd>
            <p className="mt-1 text-xs text-slate-400">Just an illustrative stress scenario, not a worst-case estimate.</p></div>
        </dl>
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
