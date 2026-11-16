import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { getScannerStatus, type ScannerStatus } from '../scanner/scannerApi'
import { getResearchOverview, type ResearchOverviewResponse } from './researchApi'

function signedPercent(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

export default function ResearchOverview() {
  const [overview, setOverview] = useState<ResearchOverviewResponse | null>(null)
  const [scan, setScan] = useState<ScannerStatus | null>(null)
  const [journalError, setJournalError] = useState(false)

  useEffect(() => {
    let mounted = true
    void getResearchOverview().then((response) => {
      if (mounted) setOverview(response)
    }).catch(() => {
      if (mounted) setJournalError(true)
    })
    void getScannerStatus().then((response) => {
      if (mounted) setScan(response)
    }).catch(() => { /* Market panel and scanner route handle their own errors. */ })
    return () => { mounted = false }
  }, [])

  const counts = overview?.status_counts
  const frozen = overview?.latest_checkpoint
  const latestGroup = overview?.groups.find((group) => group.metrics !== null) ?? overview?.groups[0]
  const metrics = latestGroup?.metrics

  return (
    <section aria-label="Research progress" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h2 className="text-2xl font-bold">Research progress</h2>
          <p className="mt-1 text-sm text-slate-400">Frozen predictions, not simulated success stories.</p>
        </div>
        <Link className="rounded-lg border border-emerald-600 px-4 py-2 text-sm text-emerald-300 hover:bg-emerald-900/30"
          to="/planner">Plan an investment budget</Link>
        <Link className="rounded-lg border border-slate-600 px-4 py-2 text-sm text-slate-200 hover:bg-slate-800"
          to="/compare">Compare three styles</Link>
      </div>
      <div className="grid gap-4 md:grid-cols-3">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Registered forward predictions</p>
          <p className="mt-2 text-3xl font-semibold">{overview?.registered_checkpoints ?? '—'}</p>
          {journalError && <p className="mt-2 text-xs text-amber-300">Journal unavailable; no statistics shown.</p>}
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Waiting for future outcomes</p>
          <p className="mt-2 text-3xl font-semibold">{counts?.PENDING ?? '—'}</p>
          <p className="mt-2 text-xs text-slate-400">Ready to evaluate: {counts?.READY ?? '—'}</p>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <p className="text-sm text-slate-400">Complete evaluations</p>
          <p className="mt-2 text-3xl font-semibold">{counts?.COMPLETE ?? '—'}</p>
          <p className="mt-2 text-xs text-slate-400">Incomplete: {counts?.INCOMPLETE ?? '—'}</p>
        </div>
      </div>
      <div className="grid gap-4 lg:grid-cols-2">
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h3 className="text-lg font-semibold">Latest market research shortlist</h3>
          {scan?.state === 'complete' ? <>
            <p className="mt-2 text-sm text-slate-300">
              {scan.considered.toLocaleString()} securities checked · {scan.qualified.toLocaleString()} qualified
            </p>
            <p className="mt-1 text-xs text-slate-400">Completed-price data through {scan.latest_session ?? 'unknown'}</p>
            <ol className="mt-4 space-y-2">
              {scan.candidates.slice(0, 3).map((item) => (
                <li key={item.symbol} className="flex items-start justify-between gap-3 border-t border-slate-800 pt-2 text-sm">
                  <span>{item.symbol} <span className="text-slate-400">· {item.name}</span></span>
                  <span className="shrink-0 text-slate-300">{signedPercent(item.return_60d_pct)} past 60 sessions</span>
                </li>
              ))}
            </ol>
          </> : frozen ? <>
            <p className="mt-2 text-sm text-slate-300">Latest pinned market-wide scan: {frozen.signal_session}</p>
            <p className="mt-1 text-xs text-slate-400">
              {frozen.eligible_symbols_considered.toLocaleString()} screened · {frozen.qualified_by_scanner.toLocaleString()} qualified
            </p>
            <ol className="mt-4 space-y-2">
              {frozen.candidates.slice(0, 3).map((item) => <li key={item.symbol}
                className="border-t border-slate-800 pt-2 text-sm">
                {item.symbol} <span className="text-slate-400">· {item.name}</span>
              </li>)}
            </ol>
          </> : <p className="mt-3 text-sm text-slate-400">
            {scan?.state === 'running' ? 'A market scan is in progress.' :
              'No completed website scan or verified saved checkpoint is available.'}
          </p>}
          <Link className="mt-4 inline-block text-sm font-medium text-emerald-400 hover:underline" to="/scanner">
            Open Find Opportunities
          </Link>
          <Link className="ml-4 mt-4 inline-block text-sm font-medium text-emerald-400 hover:underline" to="/decisions">
            Explain the shortlist
          </Link>
        </div>
        <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
          <h3 className="text-lg font-semibold">Evidence against SPY</h3>
          {metrics ? <>
            <p className="mt-3 text-sm">Completed periods: {metrics.complete_windows}</p>
            <p className="mt-2 text-sm">Mean selected net: {metrics.mean_selected_net_pct}%</p>
            <p className="mt-1 text-sm">Mean SPY net: {metrics.mean_spy_net_pct}%</p>
            <p className="mt-1 text-sm">Mean paired excess: {metrics.mean_paired_excess_pp} percentage points</p>
            <p className="mt-3 text-xs text-amber-200">Overlapping windows are correlated. These averages are not portfolio profits.</p>
          </> : <p className="mt-3 text-sm text-slate-400">
            No completed, verified outcomes yet. Returns and win rates will stay hidden until real evaluations exist.
          </p>}
        </div>
      </div>
    </section>
  )
}
