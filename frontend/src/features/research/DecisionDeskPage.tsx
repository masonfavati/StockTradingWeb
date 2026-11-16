import BeginnerHelp from '../learn/BeginnerHelp'
import { plainPredictionStatus } from '../learn/marketWords'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getDecisionDesk, type DecisionCandidate, type DecisionDeskResponse } from './researchApi'
import { historyLink } from '../history/historyApi'

const reasons: Record<string, string> = {
  unverified_share_type: 'Security name does not support an ordinary-share classification',
  duplicate_ticker: 'Repeated ticker in this shortlist',
  outdated_session: 'Candidate does not match this scan session',
  missing_or_invalid_metrics: 'Missing or invalid historical measurements',
  below_price_floor: 'Historical price below $5',
  below_liquidity_screen: 'Approximate historical daily trading value below $5 million',
  above_volatility_screen: 'Historical volatility outside the research threshold',
  outside_drawdown_screen: 'Historical drawdown outside the research threshold',
  repeated_apparent_issuer_or_ticker: 'Appears to duplicate an earlier qualifying ticker or issuer name',
}

function displayNumber(value: number | null, suffix = '', fractionDigits = 1) {
  return value === null ? 'Unavailable' : `${value.toLocaleString('en-US', { maximumFractionDigits: fractionDigits })}${suffix}`
}

function CandidateDetails({ candidate, signal }: { candidate: DecisionCandidate; signal: string | null }) {
  const m = candidate.metrics
  return <article className="rounded-xl border border-slate-700 bg-slate-950 p-5" aria-label={`Research candidate ${candidate.symbol}`}>
    <div className="flex flex-wrap items-start justify-between gap-4">
      <div>
        <p className="text-xs font-medium text-slate-400">Research list position #{candidate.rank}</p>
        <h3 className="mt-1 text-lg font-semibold">{candidate.symbol} <span className="text-sm font-normal text-slate-400">{candidate.name}</span></h3>
      </div>
      <p className={candidate.quality_passed ? 'rounded-lg border border-emerald-800 px-3 py-1 text-sm text-emerald-300' : 'rounded-lg border border-amber-800 px-3 py-1 text-sm text-amber-200'}>
        {candidate.quality_passed ? 'Passed the basic past-price checks' : 'Did not pass the basic past-price checks'}
      </p>
    </div>
    <Link to={historyLink(candidate.symbol, signal)} className="mt-3 inline-block text-sm text-emerald-400 underline">View historical price chart</Link>
    {candidate.quality_reason && <p className="mt-3 text-sm text-amber-200">
      Why excluded: {reasons[candidate.quality_reason] ?? candidate.quality_reason.replace(/_/g, ' ')}.
    </p>}
    <dl className="mt-4 grid gap-3 text-sm sm:grid-cols-2 lg:grid-cols-4">
      <div><dt className="text-slate-400">Last adjusted daily price</dt><dd>{m.adjusted_close === null ? 'Unavailable' : `$${displayNumber(m.adjusted_close, '', 2)}`}</dd></div>
      <div><dt className="text-slate-400">Price change over about 1 month</dt><dd>{displayNumber(m.return_20d_pct, '%')}</dd></div>
      <div><dt className="text-slate-400">Price change over about 3 months</dt><dd>{displayNumber(m.return_60d_pct, '%')}</dd></div>
      <div><dt className="text-slate-400">How sharply the price moved (yearly scale)</dt><dd>{displayNumber(m.annualized_volatility_pct, '%')}</dd></div>
      <div><dt className="text-slate-400">Largest recent drop from a high</dt><dd>{displayNumber(m.drawdown_60d_pct, '%')}</dd></div>
      <div><dt className="text-slate-400">Approximate daily amount traded</dt><dd>{m.approx_daily_dollar_volume === null ? 'Unavailable' : `$${displayNumber(m.approx_daily_dollar_volume, '', 0)}`}</dd></div>
      <div><dt className="text-slate-400">Research ordering score (not a profit chance)</dt><dd>{displayNumber(m.research_score, '', 3)}</dd></div>
    </dl>
    <div className="mt-4 grid gap-3 border-t border-slate-800 pt-4 text-sm md:grid-cols-2">
      <p><strong className="font-medium">Government company record:</strong>{' '}
        {candidate.sec_filer.status === 'matched'
          ? `${candidate.sec_filer.name} · CIK ${candidate.sec_filer.cik} · ${candidate.sec_filer.exchange}`
          : `Not verified (${candidate.sec_filer.status.replace(/_/g, ' ')})`}</p>
      <p><strong className="font-medium">Government-reported business type:</strong>{' '}
        {candidate.sec_industry.status === 'matched'
          ? `${candidate.sec_industry.code} — ${candidate.sec_industry.description}`
          : `Not verified (${candidate.sec_industry.status.replace(/_/g, ' ')})`}</p>
    </div>
  </article>
}

export default function DecisionDeskPage() {
  const [result, setResult] = useState<DecisionDeskResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const [filter, setFilter] = useState<'all' | 'passed' | 'excluded'>('all')
  const [search, setSearch] = useState('')
  const [refreshToken, setRefreshToken] = useState(0)

  useEffect(() => {
    let active = true
    void getDecisionDesk().then(data => {
      if (active) { setResult(data); setError(false); setLoading(false) }
    }).catch(() => {
      if (active) { setResult(null); setError(true); setLoading(false) }
    })
    return () => { active = false }
  }, [refreshToken])

  const filtered = (result?.candidates ?? []).filter(item => {
    const matchesFilter = filter === 'all' || (filter === 'passed' ? item.quality_passed : !item.quality_passed)
    const needle = search.trim().toLowerCase()
    return matchesFilter && (!needle || `${item.symbol} ${item.name}`.toLowerCase().includes(needle))
  })

  return <section className="space-y-6" aria-label="Research decision desk">
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-7">
      <p className="text-sm font-semibold text-emerald-400">Understand the stock ideas</p>
      <h1 className="mt-2 text-3xl font-bold">Understand the market shortlist</h1>
      <p className="mt-3 max-w-4xl text-sm text-slate-300">
        See which companies appeared in the market search, what their earlier prices looked like,
        and why some were left out. None of these results tells you which stock to buy.
      </p>
      <div className="mt-5 flex flex-wrap gap-3">
        <Link to="/planner" className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-medium text-white hover:bg-emerald-600">Try a budget example</Link>
        <Link to="/compare" className="rounded-lg border border-emerald-600 px-4 py-2 text-sm text-emerald-300 hover:bg-slate-800">Compare budget styles</Link>
        <Link to="/forecasts" className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800">Can we trust the predictions?</Link>
        <button type="button" onClick={() => { setLoading(true); setRefreshToken(value => value + 1) }}
          className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800">Refresh research details</button>
      </div>
      <p className="mt-3 text-xs text-slate-400">Refreshing shows already-saved research. It does not search the market again or buy any stocks.</p>
    </div>
    {loading && <p className="text-slate-400">Reading verified research evidence…</p>}
    {error && <p role="alert" className="rounded-xl border border-red-800 p-4 text-red-300">Research evidence could not be verified. No candidate report is published.</p>}
    {result && <>
      <div className="grid gap-4 sm:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5"><p className="text-sm text-slate-400">Recorded shortlist</p><p className="mt-2 text-2xl font-semibold">{result.displayed_count} shown</p><p className="mt-1 text-xs text-slate-400">From {result.considered_count} recorded candidates (maximum 20 displayed)</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5"><p className="text-sm text-slate-400">Passed the basic past-price checks</p><p className="mt-2 text-2xl font-semibold">{result.quality_passed_count}</p><p className="mt-1 text-xs text-slate-400">Not final portfolio eligibility</p></div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5"><p className="text-sm text-slate-400">Prediction model validation</p><p className="mt-2 text-lg font-semibold">{plainPredictionStatus(result.prediction_status)}</p><p className="mt-1 text-xs text-slate-400">Individual stock scores are not shown here</p></div>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5 text-sm">
        <h2 className="font-semibold">How old is this information?</h2>
        {result.source_kind ? <p className="mt-2 text-slate-300">
          {result.source_kind === 'website_scan' ? 'Completed website scan' : 'Verified saved research file'}.
          {' '}Last stock-price date: {result.signal_session ?? 'unknown'}.
          {' '}Saved: {result.recorded_at_utc ?? 'unknown'}.
          {' '}Age at retrieval: {result.source_age_hours === null ? 'unknown' : `${result.source_age_hours} hours`}.
        </p> : <p className="mt-2 text-amber-200">No completed website scan or verified saved checkpoint is available.</p>}
        {result.source_kind && !result.source_recent && <p className="mt-2 text-amber-200">These research results may be too old or their dates cannot be verified. The budget planner will not treat them as fresh.</p>}
        <p className="mt-3 text-xs text-slate-400">This page does not tell you how much to invest. The budget planner checks the dates and other safeguards again.</p>
      </div>
      <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <div className="flex flex-wrap items-end justify-between gap-3">
          <div><h2 className="text-xl font-semibold">Stocks found by the search</h2><p className="mt-1 text-sm text-slate-400">Listed by earlier price patterns, not by an estimate of future profit.</p></div>
          <div className="flex flex-wrap gap-2">
            <label className="text-xs text-slate-400">Filter
              <select aria-label="Quality filter" value={filter} onChange={event => setFilter(event.target.value as typeof filter)}
                className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white">
                <option value="all">All candidates</option><option value="passed">Quality screen passed</option><option value="excluded">Quality screen excluded</option>
              </select>
            </label>
            <label className="text-xs text-slate-400">Search symbol or name
              <input aria-label="Search research candidates" value={search} onChange={event => setSearch(event.target.value)}
                className="mt-1 block rounded-lg border border-slate-700 bg-slate-950 px-3 py-2 text-sm text-white" placeholder="Ticker or name" />
            </label>
          </div>
        </div>
        {!result.candidates.length && <p className="mt-4 text-sm text-amber-200">No recorded candidates to inspect. Run a market scan or wait for the next frozen checkpoint.</p>}
        {result.candidates.length > 0 && filtered.length === 0 && <p className="mt-4 text-sm text-slate-400">No candidates match this filter.</p>}
        <div className="mt-5 space-y-4">{filtered.map(item => <CandidateDetails key={`${item.rank}-${item.symbol}`} candidate={item} signal={result.signal_session}/>)}</div>
      </div>
      <BeginnerHelp words={['stock', 'ticker', 'scan', 'change', 'risk', 'drop', 'sec', 'sic', 'prediction']} />
      <div className="rounded-xl border border-slate-800 p-5">
        <h2 className="font-semibold">What these results cannot tell you</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-400">{result.caveats.map(caveat => <li key={caveat}>{caveat}</li>)}</ul>
        <Link className="mt-4 inline-block text-emerald-400 underline" to="/planner">See a budget example for your own amount and time frame</Link>
      </div>
    </>}
  </section>
}
