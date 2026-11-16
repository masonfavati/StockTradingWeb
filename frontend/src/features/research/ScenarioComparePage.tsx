import { useRef, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { calculateBudgetPlan, type InvestmentHorizon } from './researchApi'
import {
  COMPARISON_STYLES, STYLE_LABELS, checkComparison, comparisonCsv,
  plannerDestination, validateComparisonSettings,
  type CheckedComparison, type ComparisonSettings,
} from './scenarioComparison'

function formatCents(cents: number): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(cents / 100)
}

const initial: ComparisonSettings = {
  budget: '100.00', horizon: 'long', maxLoss: '', experimental: false,
  secIdentity: true, secIndustry: true, prediction: true, comovement: true,
}

export default function ScenarioComparePage() {
  const [settings, setSettings] = useState<ComparisonSettings>(initial)
  const [completedSettings, setCompletedSettings] = useState<ComparisonSettings | null>(null)
  const [comparison, setComparison] = useState<CheckedComparison | null>(null)
  const [pending, setPending] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const sequence = useRef(0)

  function update(partial: Partial<ComparisonSettings>) {
    sequence.current += 1
    setSettings(previous => ({ ...previous, ...partial }))
    setComparison(null)
    setCompletedSettings(null)
    setPending(false)
    setError(null)
  }

  async function compare(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const current = ++sequence.current
    setError(null)
    setComparison(null)
    setCompletedSettings(null)
    const invalid = validateComparisonSettings(settings)
    if (invalid) { setError(invalid); return }
    setPending(true)
    try {
      const plans = await Promise.all(COMPARISON_STYLES.map(style => calculateBudgetPlan(
        settings.budget, style, settings.experimental, settings.horizon,
        settings.maxLoss === '' ? null : settings.maxLoss,
        settings.experimental && settings.comovement,
        settings.experimental && settings.secIdentity,
        settings.experimental && settings.secIndustry,
        settings.experimental && settings.prediction,
      )))
      const checked = checkComparison(plans, settings, new Date().toISOString())
      if (sequence.current === current) {
        setCompletedSettings({ ...settings })
        setComparison(checked)
      }
    } catch (caught) {
      if (sequence.current === current) {
        setError(caught instanceof Error ? caught.message : 'Unable to compare scenarios.')
      }
    } finally {
      if (sequence.current === current) setPending(false)
    }
  }

  function downloadCsv() {
    if (!comparison) return
    const csv = comparisonCsv(comparison)
    const url = URL.createObjectURL(new Blob([csv], { type: 'text/csv;charset=utf-8' }))
    const element = document.createElement('a')
    element.href = url
    element.download = 'stocktradingweb-budget-comparison.csv'
    document.body.appendChild(element)
    element.click()
    element.remove()
    URL.revokeObjectURL(url)
  }

  return <section aria-label="Budget comparison workspace" className="space-y-6">
    <header className="rounded-2xl border border-slate-800 bg-slate-900 p-7">
      <p className="text-sm font-semibold text-emerald-400">Research → Compare → Plan</p>
      <h1 className="mt-2 text-3xl font-bold">Budget Comparison Workspace</h1>
      <p className="mt-3 max-w-3xl text-sm text-slate-300">
        Compare Cautious, Balanced, and Growth-oriented budget examples using the exact same
        amount, time horizon, affordable-loss limit, and evidence requirements.
        More money invested is not automatically a better choice.
      </p>
      <p className="mt-3 text-sm text-amber-200">
        These are illustrative allocations, not return forecasts, guaranteed loss limits,
        live quotes, or trade instructions. Nothing here buys a security.
      </p>
      <div className="mt-4 flex gap-4 text-sm">
        <Link to="/decisions" className="text-emerald-300 underline">Inspect the research shortlist</Link>
        <Link to="/forecasts" className="text-emerald-300 underline">Review prediction evidence</Link>
      </div>
    </header>

    <form onSubmit={(event) => { void compare(event) }} className="space-y-5 rounded-2xl border border-slate-800 bg-slate-900 p-6">
      <div className="grid gap-4 sm:grid-cols-3">
        <label className="text-sm">Budget (USD)
          <input aria-label="Comparison budget" value={settings.budget}
            onChange={event => update({ budget: event.target.value })} inputMode="decimal"
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3" />
        </label>
        <label className="text-sm">When might you need the money?
          <select aria-label="Comparison horizon" value={settings.horizon}
            onChange={event => update({ horizon: event.target.value as InvestmentHorizon })}
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3">
            <option value="short">Within 1 year</option>
            <option value="medium">In 1–5 years</option>
            <option value="long">In 5+ years</option>
          </select>
        </label>
        <label className="text-sm">Maximum affordable loss (optional, USD)
          <input aria-label="Comparison loss limit" value={settings.maxLoss}
            onChange={event => update({ maxLoss: event.target.value })} inputMode="decimal" placeholder="e.g. 25.00"
            className="mt-2 block w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3" />
        </label>
      </div>
      <label className="flex items-start gap-3 text-sm">
        <input type="checkbox" checked={settings.experimental} className="mt-1 accent-emerald-500"
          onChange={event => update({ experimental: event.target.checked })} />
        Include experimental individual-stock research ideas (not buy recommendations)
      </label>
      {settings.experimental && <div className="space-y-3 rounded-xl border border-slate-700 p-4 text-sm">
        <p className="font-semibold">Require evidence before assigning experimental dollars</p>
        <label className="flex gap-2"><input aria-label="Comparison SEC filer evidence" type="checkbox"
          checked={settings.secIdentity || settings.secIndustry} disabled={settings.secIndustry}
          onChange={event => update({ secIdentity: event.target.checked })} /> SEC filer cross-reference</label>
        <label className="flex gap-2"><input aria-label="Comparison SEC industry evidence" type="checkbox"
          checked={settings.secIndustry}
          onChange={event => update({ secIndustry: event.target.checked, secIdentity: event.target.checked || settings.secIdentity })} /> SEC SIC industry classification</label>
        <label className="flex gap-2"><input aria-label="Comparison prediction evidence" type="checkbox"
          checked={settings.prediction} onChange={event => update({ prediction: event.target.checked })} /> Validated prospective prediction evidence</label>
        <label className="flex gap-2"><input aria-label="Comparison historical correlation" type="checkbox"
          checked={settings.comovement} onChange={event => update({ comovement: event.target.checked })} /> Historical co-movement evidence</label>
        <p className="text-xs text-slate-400">
          Comparison makes three independent read-only planner requests. With historical co-movement
          enabled, qualifying stock ideas may trigger up to three bounded Alpaca history checks.
          Turning an evidence requirement off does not make an unvalidated idea trustworthy.
        </p>
      </div>}
      <button type="submit" disabled={pending} className="rounded-lg bg-emerald-700 px-5 py-3 font-semibold hover:bg-emerald-600 disabled:opacity-50">
        {pending ? 'Comparing three scenarios…' : 'Compare three allocation styles'}
      </button>
      {error && <p role="alert" className="rounded-xl border border-red-800 p-3 text-sm text-red-200">{error}</p>}
    </form>

    {comparison && completedSettings && <div className="space-y-5" aria-label="Completed comparison">
      <div className="flex flex-wrap items-center justify-between gap-4 rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div>
          <h2 className="text-xl font-semibold">Same budget, three different exposures</h2>
          <p className="mt-1 text-xs text-slate-400">
            {formatCents(comparison.budgetCents)} total in every column · snapshot captured {comparison.capturedAtUtc}
          </p>
        </div>
        <button type="button" onClick={downloadCsv} className="rounded-lg border border-emerald-600 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-900/30">
          Export comparison CSV
        </button>
      </div>
      <div className="grid gap-4 lg:grid-cols-3">
        {comparison.scenarios.map(({ plan, coreCents, stockCents, cashCents, investedCents, stress30LossCents }) => <article key={plan.style}
          className="space-y-4 rounded-xl border border-slate-700 bg-slate-900 p-5" aria-label={`${STYLE_LABELS[plan.style]} comparison`}>
          <div><h3 className="text-xl font-semibold">{STYLE_LABELS[plan.style]}</h3>
            <p className="mt-1 text-xs text-slate-400">Allocation illustration · {plan.horizon} horizon</p></div>
          <div className="space-y-2 text-sm">
            <p>Illustratively invested: <strong>{formatCents(investedCents)}</strong></p>
            <p>Retained cash: <strong>{formatCents(cashCents)}</strong></p>
            <div className="flex h-4 overflow-hidden rounded-lg" role="img" aria-label={`Allocation proportions for ${STYLE_LABELS[plan.style]}`}>
              {coreCents > 0 && <div className="bg-emerald-600" style={{ width: `${100 * coreCents / comparison.budgetCents}%` }} />}
              {stockCents > 0 && <div className="bg-sky-500" style={{ width: `${100 * stockCents / comparison.budgetCents}%` }} />}
              {cashCents > 0 && <div className="bg-slate-500" style={{ width: `${100 * cashCents / comparison.budgetCents}%` }} />}
            </div>
            <p className="text-xs text-slate-400">Core ETF example {formatCents(coreCents)} · experimental {formatCents(stockCents)} · cash {formatCents(cashCents)}</p>
          </div>
          <div className="border-t border-slate-700 pt-3 text-sm">
            <h4 className="font-semibold">Illustrative allocations</h4>
            <ul className="mt-2 space-y-2">{plan.allocation.map((row, i) => <li key={`${row.category}-${row.symbol ?? i}`}>
              <div className="flex justify-between gap-2"><span>{row.name}</span><strong className="shrink-0">{row.amount_usd ? formatCents(Math.round(Number(row.amount_usd) * 100)) : 'Unavailable'}</strong></div>
              <p className="mt-1 text-xs text-slate-400">{row.reason}</p>
            </li>)}</ul>
          </div>
          <div className="border-t border-slate-700 pt-3 text-sm">
            <p>Illustrative 30% equity decline: {stress30LossCents === null ? 'Not available' : <strong>{formatCents(stress30LossCents)} loss</strong>}</p>
            <p className="mt-2 text-xs text-amber-200">A 30% example is not a maximum loss or a probability forecast.</p>
          </div>
          <div className="space-y-2 border-t border-slate-700 pt-3 text-xs text-slate-300">
            <p>Research source: {plan.source_kind?.replace(/_/g, ' ') ?? 'No eligible shortlist'}; session {plan.source_session ?? 'unavailable'}</p>
            {plan.prediction_required && <p>Prediction evidence: {plan.prediction_review?.status.replace(/_/g, ' ') ?? 'unavailable'}</p>}
            <p>Affordable-loss cap binding: {plan.loss_cap_binding ? 'Yes' : 'No'}</p>
            {plan.planning_explanations.slice(0, 2).map(text => <p key={text}>{text}</p>)}
            {plan.warnings.slice(0, 2).map(text => <p className="text-amber-200" key={text}>{text}</p>)}
          </div>
          <Link to={plannerDestination(completedSettings, plan.style)}
            className="inline-block rounded-lg border border-emerald-600 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-900/30">
            Inspect this style in the full planner
          </Link>
        </article>)}
      </div>
      <section className="rounded-xl border border-slate-800 p-5 text-sm">
        <h2 className="font-semibold">How to interpret this comparison</h2>
        <p className="mt-2 text-slate-300">
          In these examples, Growth-oriented allocates{' '}
          {formatCents(Math.abs(comparison.scenarios[2].investedCents - comparison.scenarios[0].investedCents))}
          {' '}{comparison.scenarios[2].investedCents >= comparison.scenarios[0].investedCents ? 'more' : 'less'} to investments than Cautious, with the difference kept in cash instead.
          {comparison.scenarios[2].stress30LossCents !== null && comparison.scenarios[0].stress30LossCents !== null && <>
            {' '}Under the same illustrative 30% equity decline, the Growth-oriented example loses{' '}
            {formatCents(Math.abs(comparison.scenarios[2].stress30LossCents - comparison.scenarios[0].stress30LossCents))}
            {' '}{comparison.scenarios[2].stress30LossCents >= comparison.scenarios[0].stress30LossCents ? 'more' : 'less'} than Cautious.
          </>}
        </p>
        <p className="mt-2 text-slate-300">The allocation differences reflect preset illustrative risk styles, not a model's proof that one approach will earn more. Cash is budget money deliberately left uninvested; the investment amount is only a proposal, not an executed purchase.</p>
        <p className="mt-2 text-slate-400">Open any style in the full planner to review the complete candidate-by-candidate evidence, exclusions, and downside explanations before acting. This export preserves the returned allocation amounts and reasons, but not a live market quote or an investment recommendation.</p>
      </section>
    </div>}
  </section>
}
