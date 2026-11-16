import BeginnerHelp from '../learn/BeginnerHelp'
import { plainPredictionStatus } from '../learn/marketWords'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getPredictionValidation, type PredictionValidation } from './researchApi'

const checkLabels: Record<string, string> = {
  at_least_20_walk_forward_windows: 'Tested at least 20 later time periods',
  at_least_200_tested_candidates: 'Checked at least 200 stock outcomes',
  at_least_8_nonoverlapping_holding_windows: 'Included at least eight periods that do not overlap',
  better_brier_than_expanding_training_prior: 'Probability guesses were more accurate than a simple comparison',
  positive_average_top_two_excess_vs_spy: 'Top selected stocks did better than SPY on average in these tests',
  not_worse_than_original_scan_top_two: 'Did at least as well as the original stock-search order',
}

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
      <p className="text-sm font-semibold text-emerald-400">Can we trust these predictions?</p>
      <h1 className="mt-2 text-3xl font-bold">What have the predictions actually gotten right?</h1>
      <p className="mt-3 text-slate-300">
        The app is testing whether stocks it picked could do better than SPY (a fund tracking
        many large U.S. companies) over about 20 trading days. The model does not predict a future stock price
        or promise a profit. Beating SPY does not always mean making money.
      </p>
      <p className="mt-3 text-sm text-amber-200">
        We only let experimental predictions influence budget examples after enough earlier guesses
        have been checked against real results that happened later. Until then, the app leaves that money as cash.
      </p>
      <Link to="/planner" className="mt-4 inline-block text-emerald-400 underline">Open Investment Planner</Link>
    </div>
    {error && <p role="alert" className="rounded-xl border border-red-900 p-4 text-red-300">
      We could not check the saved prediction results. The app will not show unverified scores.
    </p>}
    {!report && !error && <p className="text-slate-400">Checking saved predictions against later results…</p>}
    {report && <>
      <div className="grid gap-4 sm:grid-cols-3">
        <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Are these predictions reliable enough yet?</p>
          <p className="mt-2 text-lg font-semibold" data-testid="prediction-status">
            {plainPredictionStatus(report.status)}
          </p>
        </article>
        <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Earlier market searches checked against later prices</p>
          <p className="mt-2 text-3xl font-semibold">{report.completed_compatible_windows}</p>
          <p className="mt-1 text-xs text-slate-400">{report.completed_candidate_outcomes} stock results checked</p>
        </article>
        <article className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Time periods used to test the model</p>
          <p className="mt-2 text-3xl font-semibold">{report.walk_forward.validation_windows}</p>
          <p className="mt-1 text-xs text-slate-400">
            {report.walk_forward.nonoverlapping_validation_windows} separate test periods
          </p>
        </article>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-xl font-semibold">Did the model beat simpler ways of guessing?</h2>
        <p className="mt-2 text-sm text-slate-400">
          In each test, the model was allowed to learn only from results already known at the time.
          Some tests overlap, so they are not completely independent.
        </p>
        <dl className="mt-4 grid gap-4 sm:grid-cols-2">
          <div><dt className="text-sm text-slate-400">How accurate were the model’s probability estimates? (lower is better)</dt>
            <dd className="font-medium">{number(report.walk_forward.brier_score)}</dd></div>
          <div><dt className="text-sm text-slate-400">A simpler guess to compare against (lower is better)</dt>
            <dd className="font-medium">{number(report.walk_forward.expanding_prior_brier_score)}</dd></div>
          <div><dt className="text-sm text-slate-400">Did the model’s top two stocks do better than SPY on average?</dt>
            <dd className="font-medium">{number(report.walk_forward.top_two_mean_excess_vs_spy_pp)} percentage points</dd></div>
          <div><dt className="text-sm text-slate-400">Did the model improve on the original stock search?</dt>
            <dd className="font-medium">{number(report.walk_forward.top_two_mean_vs_original_scan_pp)} percentage points</dd></div>
        </dl>
        <h3 className="mt-6 font-semibold">Rules the model must pass before we use its predictions</h3>
        <ul className="mt-3 space-y-2 text-sm">
          {Object.entries(report.walk_forward.checks).map(([name, passed]) => <li key={name}>
            <span className={passed ? 'text-emerald-300' : 'text-amber-200'}>
              {passed ? 'Passed' : 'Not met'}
            </span>{' '}— {checkLabels[name] ?? 'Additional research check'}
          </li>)}
        </ul>
        {report.status !== 'research_gate_passed' && <p className="mt-4 text-sm text-amber-200">
          The model has not passed enough real-world tests yet. The budget planner will leave
          prediction-dependent money uninvested. Additional genuinely matured outcomes are needed.
        </p>}
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-lg font-semibold">Important limits of this research</h2>
        <p className="mt-2 text-sm text-slate-300">Even a model that passed past tests could make mistakes next time.</p>
        <details className="mt-3 text-sm text-slate-400"><summary className="cursor-pointer text-emerald-300">Show the technical test method</summary><p className="mt-2">{report.method}</p></details>
        <details className="mt-3 text-sm text-slate-400"><summary className="cursor-pointer text-emerald-300">Show the detailed limitations and data verification code</summary>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-amber-200">
            {report.warnings.map(item => <li key={item}>{item}</li>)}
          </ul>
          <p className="mt-3 break-all text-xs text-slate-500">Saved-data verification code: {report.source_sha256}</p>
        </details>
      </div>
    </>}
    <BeginnerHelp words={['scan', 'prediction', 'forecast', 'spy', 'cash']} />
  </section>
}
