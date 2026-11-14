import { useEffect, useState } from 'react'
import { getScannerStatus, startScanner, type ScannerStatus } from './scannerApi'

function signedPercent(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function formatMoney(value: number): string {
  return new Intl.NumberFormat('en-US', {
    style: 'currency', currency: 'USD', maximumFractionDigits: 2,
  }).format(value)
}

export default function ScannerPage() {
  const [status, setStatus] = useState<ScannerStatus | null>(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let active = true
    async function refresh() {
      try {
        const next = await getScannerStatus()
        if (active) { setStatus(next); setError(null) }
      } catch (err) {
        if (active) setError(err instanceof Error ? err.message : 'The scanner is unavailable.')
      }
    }
    void refresh()
    const timer = window.setInterval(() => { void refresh() }, 2500)
    return () => { active = false; window.clearInterval(timer) }
  }, [])

  async function start() {
    setLoading(true)
    setError(null)
    try {
      setStatus(await startScanner())
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to start the scan.')
    } finally {
      setLoading(false)
    }
  }

  const running = status?.state === 'running'
  const complete = status?.state === 'complete'
  const progress = running && status.considered > 0
    ? Math.round(100 * status.processed / status.considered) : 0

  return (
    <section className="space-y-6" aria-label="Market opportunity research">
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-8">
        <p className="text-sm font-semibold text-emerald-400">Explore the US stock market</p>
        <h1 className="mt-2 text-3xl font-bold">Find Opportunities</h1>
        <p className="mt-3 max-w-3xl text-slate-300">
          Search the active, tradable US stocks in Alpaca's directory—not just the companies
          you're following. Find candidates whose recent price trends deserve further research.
        </p>
        <p className="mt-3 max-w-3xl text-sm text-amber-200">
          This is a historical research screen, not a prediction or buy recommendation. A low
          stock price does not make a gain more likely. We haven't validated a profitable
          strategy or estimated the probability of a stock increasing yet.
        </p>
        <div className="mt-6 flex flex-wrap items-center gap-4">
          <button type="button" onClick={() => { void start() }} disabled={loading || running}
            className="rounded-lg bg-emerald-600 px-5 py-3 font-semibold text-white hover:bg-emerald-500 disabled:cursor-not-allowed disabled:opacity-50">
            {running ? 'Scanning market…' : loading ? 'Starting…' : 'Find Opportunities'}
          </button>
          <span className="text-sm text-slate-400">Scans use completed-day SIP data, not live quotes.</span>
        </div>
      </div>

      {error && <p role="alert" className="rounded-lg border border-red-800 p-4 text-red-300">{error}</p>}
      {status && <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-xl font-semibold">Scan status</h2>
        <p className="mt-2 text-slate-300" role="status">{status.message}</p>
        {running && <>
          <p className="mt-3 text-sm text-slate-400">
            {status.considered > 0
              ? `${status.processed.toLocaleString()} of ${status.considered.toLocaleString()} eligible stocks checked`
              : 'Loading the eligible-stock list…'}
          </p>
          {status.considered > 0 && <div className="mt-2 h-2 rounded-full bg-slate-800"
            role="progressbar" aria-label="Stocks evaluated" aria-valuemin={0} aria-valuemax={100}
            aria-valuenow={progress}>
            <div className="h-full rounded-full bg-emerald-500" style={{ width: `${progress}%` }} />
          </div>}
        </>}
        {complete && <>
          <p className="mt-3 text-sm text-slate-400">
            {status.considered.toLocaleString()} eligible symbols checked from a directory of{' '}
            {status.directory_size.toLocaleString()} active US equity entries.
            {' '}{status.qualified.toLocaleString()} passed the initial research filters.
          </p>
          <p className="mt-2 text-sm text-slate-400">
            Newest daily price date: {status.latest_session ?? 'No usable data'}.
            {' '}Results may be reused for 15 minutes after a completed scan.
          </p>
        </>}
      </div>}

      {complete && status.candidates.length > 0 && <div className="space-y-4">
        <div>
          <h2 className="text-2xl font-bold">Research shortlist</h2>
          <p className="mt-2 text-sm text-slate-400">
            Ordered by recent 60-session performance relative to price fluctuation.
            This descriptive ranking has NOT been backtested for investment profitability.
            Stocks outside the screen may perform better.
          </p>
        </div>
        {status.candidates.map((candidate, index) => <article key={candidate.symbol}
          className="rounded-xl border border-slate-700 bg-slate-900 p-5">
          <div className="flex flex-wrap items-start justify-between gap-3">
            <div>
              <p className="text-xs font-medium text-emerald-400">Research rank {index + 1}</p>
              <h3 className="mt-1 text-xl font-semibold">{candidate.name}</h3>
              <p className="text-sm text-slate-400">{candidate.symbol} · Data through {candidate.last_session}</p>
            </div>
            <div className="text-right">
              <p className="text-xs text-slate-400">Adjusted historical close</p>
              <p className="text-xl font-bold">{formatMoney(candidate.adjusted_close)}</p>
            </div>
          </div>
          <dl className="mt-4 grid grid-cols-2 gap-4 text-sm sm:grid-cols-4">
            <div><dt className="text-slate-400">Past ~month</dt>
              <dd className="mt-1 font-semibold">{signedPercent(candidate.return_20d_pct)}</dd></div>
            <div><dt className="text-slate-400">Past ~3 months</dt>
              <dd className="mt-1 font-semibold">{signedPercent(candidate.return_60d_pct)}</dd></div>
            <div><dt className="text-slate-400">Price fluctuation (annualized)</dt>
              <dd className="mt-1 font-semibold">{candidate.annualized_volatility_pct.toFixed(1)}%</dd></div>
            <div><dt className="text-slate-400">Below recent high</dt>
              <dd className="mt-1 font-semibold">{Math.abs(candidate.drawdown_60d_pct).toFixed(1)}%</dd></div>
          </dl>
        </article>)}
      </div>}
      {complete && status.candidates.length === 0 && <p className="text-slate-300">
        No companies passed this preliminary screen. It is reasonable not to trade.
      </p>}
      <p className="text-xs leading-relaxed text-slate-500">
        The research screen excludes unavailable, thinly traded, very low-priced,
        negative-trend, and extreme-volatility candidates by preset rules. These exclusions
        are not proof that excluded stocks are poor investments. Corporate-action-adjusted
        historical prices reflect today's information and must not be reused blindly in
        point-in-time backtests. No orders are placed.
      </p>
    </section>
  )
}
