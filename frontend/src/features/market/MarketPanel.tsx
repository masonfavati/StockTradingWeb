import {
  displayPrice,
  getDataLabel,
} from './marketData'
import { useMarketStream } from './useMarketStream'

function formatTime(value: string | undefined): string {
  if (!value) return 'No observation'

  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Invalid timestamp'

  return date.toLocaleString()
}

function formatAge(value: number | null | undefined): string {
  if (value === null || value === undefined || !Number.isFinite(value)) {
    return 'Not available'
  }
  return `${Math.max(0, value).toFixed(1)} seconds`
}

export default function MarketPanel() {
  const { snapshot, connection, error } = useMarketStream()

  const status = getDataLabel(snapshot, connection)
  const isLive = status === 'LIVE IEX'
  const isSimulated = status === 'SIMULATED DATA'

  const statusColor = isLive
    ? 'border-emerald-700 bg-emerald-950 text-emerald-300'
    : isSimulated
      ? 'border-amber-700 bg-amber-950 text-amber-300'
      : 'border-slate-600 bg-slate-800 text-slate-200'

  return (
    <section
      aria-label="Market monitor"
      className="rounded-2xl border border-slate-800 bg-slate-900 p-6"
    >
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <p className="text-xs font-semibold uppercase tracking-widest text-emerald-400">
            Market monitoring
          </p>
          <h2 className="mt-2 text-2xl font-bold text-white">
            {snapshot?.symbol ?? 'Waiting for market data'}
          </h2>
          <p className="mt-1 text-sm text-slate-400">
            Alpaca · {snapshot?.coverage === 'iex_only'
              ? 'IEX exchange only'
              : snapshot?.coverage === 'synthetic_test'
                ? 'Synthetic test feed'
                : 'Coverage not yet reported'}
          </p>
        </div>

        <span
          role="status"
          className={`rounded-full border px-3 py-1.5 text-xs font-semibold ${statusColor}`}
        >
          {status}
        </span>
      </div>

      {error && (
        <p
          role="alert"
          className="mt-4 rounded-lg border border-amber-800 bg-amber-950/40 p-3 text-sm text-amber-200"
        >
          {error}
        </p>
      )}

      {snapshot?.error && (
        <p className="mt-4 text-sm text-amber-300">
          Provider connection issue: {snapshot.error}
        </p>
      )}

      <div className="mt-6 grid gap-3 sm:grid-cols-3">
        <div className="rounded-xl bg-slate-950 p-5">
          <p className="text-sm text-slate-400">Last trade</p>
          <p className="mt-2 text-2xl font-bold text-white">
            {displayPrice(snapshot?.latest_trade?.price)}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            {snapshot?.trade_fresh && isLive
              ? 'Recent observation'
              : 'Not confirmed fresh'}
          </p>
        </div>

        <div className="rounded-xl bg-slate-950 p-5">
          <p className="text-sm text-slate-400">Best available bid</p>
          <p className="mt-2 text-2xl font-bold text-white">
            {displayPrice(snapshot?.latest_quote?.bid)}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            {isSimulated ? 'Synthetic quote' : 'Feed-reported bid'}
          </p>
        </div>

        <div className="rounded-xl bg-slate-950 p-5">
          <p className="text-sm text-slate-400">Best available ask</p>
          <p className="mt-2 text-2xl font-bold text-white">
            {displayPrice(snapshot?.latest_quote?.ask)}
          </p>
          <p className="mt-2 text-xs text-slate-500">
            {isSimulated ? 'Synthetic quote' : 'Feed-reported ask'}
          </p>
        </div>
      </div>

      <div className="mt-5 grid gap-4 rounded-xl border border-slate-800 p-4 text-sm md:grid-cols-2">
        <div>
          <p className="text-slate-400">Last trade timestamp</p>
          <p className="mt-1 text-slate-200">
            {formatTime(snapshot?.latest_trade?.timestamp)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Age: {formatAge(snapshot?.trade_age_seconds)}
          </p>
        </div>

        <div>
          <p className="text-slate-400">Last quote timestamp</p>
          <p className="mt-1 text-slate-200">
            {formatTime(snapshot?.latest_quote?.timestamp)}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            Age: {formatAge(snapshot?.quote_age_seconds)}
          </p>
        </div>

        <div>
          <p className="text-slate-400">Provider connection</p>
          <p className="mt-1 text-slate-200">
            {snapshot?.connection_status ?? 'Unknown'}
          </p>
        </div>

        <div>
          <p className="text-slate-400">Browser stream</p>
          <p className="mt-1 text-slate-200">{connection}</p>
        </div>
      </div>

      <p className="mt-5 text-xs leading-relaxed text-slate-500">
        {isSimulated
          ? 'SIMULATED DATA: FAKEPACA prices are for testing only, not investment decisions.'
          : 'Real market observations are limited to the provider feed. IEX data is not a consolidated national market quote.'}
      </p>

      {!snapshot && (
        <p className="mt-3 text-sm text-slate-400">
          No observations received yet.
        </p>
      )}
    </section>
  )
}
