import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getPredictionValidation, type PredictionValidation } from './researchApi'

function number(value: number | null, digits = 3): string {
  return value === null ? 'Not available' : value.toFixed(digits)
}

export default function PredictionLabPage() {
  const [report, setReport] = useState<PredictionValidation | null>(null)
  const [error, setError] = useState(false)
  useEffect(() => {
    let mounted = true
    void getPredictionValidation().then(result => {
      if (mounted) setReport(result)
    }).catch(() => { if (mounted) setError(true) })
    return () => { mounted = false }
  }, [])

  return <section aria-label="Prospective prediction validation" className="space-y-6">
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-7">
      <p className="text-sm font-semibold text-emerald-400">Milestone 3F — Forecast Lab</p>
      <h1 className="mt-2 text-3xl font-bold">Prospective prediction and validation</h1>
      <p className="mt-3 text-slate-300">
        An experimental model estimates whether a stock already selected by the scanner could
        outperform SPY over 20 exchange sessions, after fixed illustrative costs.
        It does not predict a future stock price or promise that a dollar investment will profit.
      </p>
      <p className="mt-3 text-sm text-amber-200">
        The model is withheld from budget allocations until it clears predeclared walk-forward
        checks on genuinely recorded, matured outcomes. Historical success is not proof of future performance.
      </p>
      <Link to="/planner" className="mt-4 inline-block text-emerald-400 underline">Open Investment Planner</Link>
    </div>
    {error && <p role="alert" className="rounded-xl border border-red-900 p-4 text-red-300">
      Local prediction evidence could not be audited. No model scores are being published.
    </p>}
    {!report && !error && <p className="text-slate-400">Auditing the local forward-research journal…</p>}
    {report && <>
      <div className="grid gap-4 sm:grid-cols-3">
        <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Model evidence status</p>
          <p className="mt-2 text-lg font-semibold" data-testid="prediction-status">
            {report.status.replace(/_/g, ' ')}
          </p>
        </article>
        <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Completed prospective scan windows</p>
          <p className="mt-2 text-3xl font-semibold">{report.completed_compatible_windows}</p>
          <p className="mt-1 text-xs text-slate-400">{report.completed_candidate_outcomes} audited stock outcomes</p>
        </article>
        <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Walk-forward test windows</p>
          <p className="mt-2 text-3xl font-semibold">{report.walk_forward.validation_windows}</p>
          <p className="mt-1 text-xs text-slate-400">
            {report.walk_forward.nonoverlapping_validation_windows} nonoverlapping windows
          </p>
        </article>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-xl font-semibold">Out-of-sample evidence against baselines</h2>
        <p className="mt-2 text-sm text-slate-400">
          Each test uses only training labels whose exit dates precede its signal date.
          Overlapping test periods are correlated, not independent bets.
        </p>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <div><dt className="text-sm text-slate-400">Model Brier score (lower is better)</dt>
            <dd className="font-medium">{number(report.walk_forward.brier_score)}</dd></div>
          <div><dt className="text-sm text-slate-400">Historical training-prior Brier baseline</dt>
            <dd className="font-medium">{number(report.walk_forward.expanding_prior_brier_score)}</dd></div>
          <div><dt className="text-sm text-slate-400">Model-selected top-two average excess vs SPY</dt>
            <dd className="font-medium">{number(report.walk_forward.top_two_mean_excess_vs_spy_pp)} percentage points</dd></div>
          <div><dt className="text-sm text-slate-400">Model top-two vs original scanner top-two</dt>
            <dd className="font-medium">{number(report.walk_forward.top_two_mean_vs_original_scan_pp)} percentage points</dd></div>
        </dl>
        <h3 className="mt-6 font-semibold">Predeclared research checks</h3>
        <ul className="mt-3 space-y-2 text-sm">
          {Object.entries(report.walk_forward.checks).map(([name, passed]) => <li key={name}>
            <span className={passed ? 'text-emerald-300' : 'text-amber-200'}>
              {passed ? 'Passed' : 'Not met'}
            </span>{' '}— {name.replace(/_/g, ' ')}
          </li>)}
        </ul>
        {report.status !== 'research_gate_passed' && <p className="mt-4 text-sm text-amber-200">
          The prediction gate is not met. The planner will not spend an experimental stock slice
          when you require prediction evidence. Additional genuinely matured outcomes are needed.
        </p>}
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-lg font-semibold">Evidence limitations</h2>
        <p className="mt-2 text-sm text-slate-400">{report.method}</p>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-amber-200">
          {report.warnings.map(item => <li key={item}>{item}</li>)}
        </ul>
        <p className="mt-3 break-all text-xs text-slate-500">Audited source fingerprint: {report.source_sha256}</p>
      </div>
    </>}
  </section>
}
