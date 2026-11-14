import { useState, type FormEvent } from 'react'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import { displayPrice } from '../market/marketData'
import {
  fetchWatchlist,
  removeCompany,
  saveCompany,
  searchCompanies,
  type WatchedCompany,
} from './watchlistApi'
import {
  formatObservationTime,
  statusDescriptions,
  stockStatus,
  type MonitoredStock,
  type WatchStatus,
} from './monitoring'
import { useMonitoredFeed } from './useMonitoredFeed'

function CompanyCard({
  company,
  observed,
  status,
  onRemove,
  removing,
}: {
  company: WatchedCompany
  observed: MonitoredStock | undefined
  status: WatchStatus
  onRemove: (symbol: string) => void
  removing: boolean
}) {
  const [confirming, setConfirming] = useState(false)
  const trade = observed?.latest_trade
  const showTrade = status === 'live' || status === 'stale'
  return (
    <article className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold text-white">{company.name}</h3>
          <p className="mt-1 text-sm text-slate-400">Stock symbol: {company.symbol}</p>
        </div>
        <span className={`rounded-lg px-3 py-1 text-xs font-medium ${
          status === 'live'
            ? 'bg-emerald-950 text-emerald-300'
            : 'bg-slate-800 text-slate-200'
        }`}>
          {statusDescriptions[status]}
        </span>
      </div>

      <div className="mt-4 flex flex-wrap items-end justify-between gap-4">
        <div>
          <p className="text-sm text-slate-400">Last recorded trade on IEX</p>
          <p className="mt-1 text-2xl font-bold text-white">
            {showTrade ? displayPrice(trade?.price) : '—'}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            {showTrade ? formatObservationTime(trade?.timestamp)
              : 'No usable trade price currently available'}
          </p>
        </div>
        {confirming ? (
          <div className="flex items-center gap-2">
            <span className="text-sm text-slate-300">Remove from your list?</span>
            <button type="button" disabled={removing} onClick={() => onRemove(company.symbol)}
              className="rounded-lg bg-red-700 px-3 py-2 text-sm font-semibold text-white disabled:opacity-50">
              {removing ? 'Removing…' : 'Yes, remove'}
            </button>
            <button type="button" onClick={() => setConfirming(false)}
              className="rounded-lg border border-slate-600 px-3 py-2 text-sm text-slate-200">
              Cancel
            </button>
          </div>
        ) : (
          <button type="button" onClick={() => setConfirming(true)}
            aria-label={`Remove ${company.name}`}
            className="rounded-lg border border-slate-600 px-3 py-2 text-sm text-slate-300 hover:bg-slate-800">
            Remove
          </button>
        )}
      </div>
    </article>
  )
}

export default function WatchlistPage() {
  const queryClient = useQueryClient()
  const [companyText, setCompanyText] = useState('')
  const [searchTerm, setSearchTerm] = useState('')
  const [notice, setNotice] = useState<string | null>(null)
  const { feed, connection, error: streamError } = useMonitoredFeed()
  const browserConnected = connection === 'connected'

  const watchlist = useQuery({
    queryKey: ['watchlist'],
    queryFn: fetchWatchlist,
    refetchInterval: 30_000,
    retry: 1,
  })
  const search = useQuery({
    queryKey: ['company-search', searchTerm],
    queryFn: () => searchCompanies(searchTerm),
    enabled: searchTerm.length >= 2,
    retry: false,
  })
  const add = useMutation({
    mutationFn: saveCompany,
    onSuccess: async (result) => {
      setNotice(`${result.name} was added to your list. This did not buy any shares.`)
      await queryClient.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })
  const remove = useMutation({
    mutationFn: removeCompany,
    onSuccess: async () => {
      setNotice('Company removed from your watchlist. No shares were sold.')
      await queryClient.invalidateQueries({ queryKey: ['watchlist'] })
    },
  })

  function handleSearch(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setNotice(null)
    add.reset()
    if (companyText.trim().length >= 2) setSearchTerm(companyText.trim())
  }

  const savedSymbols = new Set((watchlist.data ?? []).map((item) => item.symbol))
  const monitoringCount = feed?.stocks.length ?? 0

  return (
    <div className="space-y-7">
      <div>
        <h1 className="text-3xl font-bold text-white">Stocks I'm Following</h1>
        <p className="mt-2 max-w-3xl text-slate-400">
          Save companies you're curious about. Following a stock does not buy it,
          risk your money, or mean it's a good investment.
        </p>
      </div>

      <section aria-labelledby="find-company-heading" className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h2 id="find-company-heading" className="text-xl font-semibold">Find a company</h2>
        <p className="mt-2 text-sm text-slate-400">
          You can type a company name, such as Apple, or its stock-market abbreviation, such as AAPL.
        </p>
        <form onSubmit={handleSearch} className="mt-4 flex flex-wrap items-end gap-3">
          <div className="min-w-52 flex-1">
            <label htmlFor="company-search" className="mb-2 block text-sm font-medium">
              Company name or stock symbol
            </label>
            <input id="company-search" type="search" value={companyText}
              onChange={(event) => setCompanyText(event.target.value)}
              placeholder="Try Apple or Microsoft" minLength={2} maxLength={80}
              className="w-full rounded-lg border border-slate-600 bg-slate-950 px-4 py-3 text-white focus:border-emerald-500 focus:outline-none" />
          </div>
          <button type="submit" disabled={companyText.trim().length < 2}
            className="rounded-lg bg-emerald-600 px-5 py-3 font-semibold text-white hover:bg-emerald-500 disabled:opacity-50">
            Find companies
          </button>
        </form>

        {searchTerm && <div className="mt-5" aria-live="polite">
          {search.isLoading && <p className="text-sm text-slate-400">Finding companies…</p>}
          {search.isError && <p role="alert" className="text-sm text-amber-300">
            {search.error.message} Your saved companies are unaffected.
          </p>}
          {search.data?.length === 0 && <p className="text-sm text-slate-400">
            No matching companies found. Try a shorter name.
          </p>}
          {search.data && search.data.length > 0 && <div className="space-y-2">
            <h3 className="text-sm font-semibold text-slate-300">Matching companies</h3>
            {search.data.map((result) => (
              <div key={result.symbol} className="flex items-center justify-between gap-3 rounded-lg border border-slate-700 bg-slate-950 p-3">
                <div>
                  <p className="font-medium text-white">{result.name}</p>
                  <p className="text-xs text-slate-400">{result.symbol}</p>
                </div>
                <button type="button" disabled={savedSymbols.has(result.symbol) || add.isPending}
                  onClick={() => { setNotice(null); add.mutate(result.symbol) }}
                  className="rounded-lg border border-emerald-600 px-3 py-2 text-sm font-semibold text-emerald-300 disabled:border-slate-700 disabled:text-slate-500">
                  {savedSymbols.has(result.symbol) ? 'Already following' : 'Follow'}
                </button>
              </div>
            ))}
          </div>}
          {add.isError && <p role="alert" className="mt-3 text-sm text-amber-300">
            Could not save company: {add.error.message}
          </p>}
        </div>}
        {notice && <p role="status" className="mt-4 rounded-lg border border-emerald-800 bg-emerald-950/40 p-3 text-sm text-emerald-200">
          {notice}
        </p>}
      </section>

      <section aria-labelledby="saved-companies-heading" className="space-y-4">
        <div>
          <h2 id="saved-companies-heading" className="text-xl font-semibold text-white">My saved companies</h2>
          <p className="mt-1 text-sm text-slate-400">
            {watchlist.data?.length ?? 0} saved · {browserConnected && feed?.feed === 'iex'
              ? `${monitoringCount} selected for the live feed (maximum ${feed.free_stream_limit})`
              : 'Live monitoring not currently confirmed'}
          </p>
          <p className="mt-1 text-xs text-slate-500">
            The free feed shows IEX trades only, not the complete U.S. market.
            Its last trade price is not a guaranteed buying or selling price.
          </p>
        </div>

        {feed?.feed === 'test' && browserConnected && <p role="status"
          className="rounded-lg border border-amber-700 bg-amber-950/40 p-4 text-sm text-amber-200">
          DEMO MODE: The test feed uses FAKEPACA, not the companies below.
          To monitor real stocks, use the IEX feed in your private backend settings.
        </p>}
        {(streamError || connection !== 'connected' ||
          (feed && feed.connection_status !== 'connected' && feed.connection_status !== 'disabled')) &&
          <p role="status" className="rounded-lg border border-slate-700 p-3 text-sm text-slate-300">
            Market connection: {feed?.connection_status ?? connection}. 
            {streamError ?? feed?.error ?? 'No live prices are confirmed right now.'}
          </p>}

        {watchlist.isLoading && <p className="text-slate-400">Loading saved companies…</p>}
        {watchlist.isError && <p role="alert" className="text-amber-300">
          Couldn't load your saved companies: {watchlist.error.message}
        </p>}
        {watchlist.data?.length === 0 && <p className="rounded-xl border border-dashed border-slate-700 p-7 text-slate-400">
          Nothing saved yet. Search for a company above and choose Follow.
        </p>}
        {watchlist.data?.map((company) => (
          <CompanyCard key={company.id}
            company={company}
            observed={feed?.stocks.find((item) => item.symbol === company.symbol)}
            status={stockStatus(company.symbol, feed, browserConnected)}
            onRemove={(symbol) => { setNotice(null); remove.mutate(symbol) }}
            removing={remove.isPending && remove.variables === company.symbol}
          />
        ))}
        {remove.isError && <p role="alert" className="text-amber-300">
          {remove.error.message}
        </p>}
      </section>
      <p className="text-xs text-slate-500">
        This page tracks interests only. StockTradingWeb cannot yet make validated buy or sell recommendations.
      </p>
    </div>
  )
}
