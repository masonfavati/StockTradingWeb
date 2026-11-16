import { useCallback, useEffect, useState, type FormEvent } from 'react'
import { Link } from 'react-router'
import { addPortfolioTrade, getPortfolio, refreshPortfolio, undoPortfolioTrade,
  type ManualTrade, type PortfolioResponse, type PortfolioRefreshResponse } from './investingApi'
import { currency } from './money'

const currentDate = new Date()
const today = `${currentDate.getFullYear()}-${String(currentDate.getMonth() + 1).padStart(2, '0')}-${String(currentDate.getDate()).padStart(2, '0')}`
function noteError(cause: unknown) {return cause instanceof Error ? cause.message : 'Something went wrong.'}

export default function HoldingsPage() {
  const [portfolio, setPortfolio] = useState<PortfolioResponse | null>(null)
  const [market, setMarket] = useState<PortfolioRefreshResponse | null>(null)
  const [error, setError] = useState('')
  const [saving, setSaving] = useState(false)
  const [refreshing, setRefreshing] = useState(false)
  const [action, setAction] = useState<ManualTrade['action']>('buy')
  const [symbol, setSymbol] = useState('')
  const [tradeDate, setTradeDate] = useState(today)
  const [shares, setShares] = useState('1')
  const [price, setPrice] = useState('')
  const [fee, setFee] = useState('0')
  const [ratio, setRatio] = useState('2')
  const load = useCallback(async () => {
    const result = await getPortfolio()
    setPortfolio(result)
    return result
  }, [])
  useEffect(() => {
    let active = true
    void getPortfolio().then(result => {
      if (!active) return
      setPortfolio(result)
      // Check existing holdings when the user opens the page, but never run a
      // provider request for an empty portfolio or execute a sell order.
      if (result.summary.holdings.length) {
        void refreshPortfolio().then(review => {
          if (active) setMarket(review)
        }).catch(cause => {
          if (active) setError(`Couldn't update completed daily prices: ${noteError(cause)}`)
        })
      }
    }).catch(cause => {if (active) setError(noteError(cause))})
    return () => {active = false}
  }, [])

  async function record(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    setError(''); setSaving(true)
    try {
      await addPortfolioTrade({action, symbol: symbol.toUpperCase().trim(), date: tradeDate,
        ...(action === 'split' ? {ratio} : {shares, price_usd: price, fee_usd: fee})})
      await load()
      setMarket(null)
      setSymbol(''); setPrice(''); setShares('1')
    } catch (cause) {setError(noteError(cause))}
    finally {setSaving(false)}
  }
  async function updatePrices() {
    setError(''); setRefreshing(true)
    try {setMarket(await refreshPortfolio())}
    catch (cause) {setError(noteError(cause))}
    finally {setRefreshing(false)}
  }
  async function undoLatest() {
    const last = portfolio?.trades[portfolio.trades.length - 1]
    if (!last) return
    setError(''); setSaving(true)
    try {await undoPortfolioTrade(last.id); await load(); setMarket(null)}
    catch (cause) {setError(noteError(cause))}
    finally {setSaving(false)}
  }
  const summary = market?.summary ?? portfolio?.summary
  const values = summary?.holdings
  const sum = values?.reduce((acc, row) => acc + Number(row.estimated_value_usd ?? 0), 0) ?? 0
  return <section className="space-y-6" aria-label="My recorded investments">
    <header className="rounded-2xl border border-slate-700 bg-slate-900 p-6">
      <p className="text-xs font-semibold uppercase tracking-widest text-emerald-300">My holdings</p>
      <h1 className="mt-2 text-3xl font-bold">Track what you actually bought</h1>
      <p className="mt-2 text-sm text-slate-300">Enter real purchases and sales yourself. This is a private local record, not connected to a brokerage account.</p>
      <div className="mt-4 flex flex-wrap gap-3"><Link to="/" className="rounded-lg border border-emerald-700 px-4 py-2 text-sm text-emerald-200">Build another budget plan</Link>
        <button type="button" onClick={updatePrices} disabled={refreshing || !values?.length}
          className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-semibold disabled:opacity-40">{refreshing ? 'Checking last daily prices…' : 'Update values and review risks'}</button></div>
    </header>

    <div className="grid gap-4 sm:grid-cols-3">
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5"><p className="text-xs text-slate-400">Estimated holdings value</p>
        <p className="mt-2 text-2xl font-bold">{summary?.estimated_portfolio_value_usd !== null && summary?.estimated_portfolio_value_usd !== undefined ? currency(summary.estimated_portfolio_value_usd) : 'Update prices'}</p></div>
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5"><p className="text-xs text-slate-400">Profit or loss from recorded sales</p>
        <p className="mt-2 text-2xl font-bold">{currency(summary?.realized_gain_usd ?? '0')}</p></div>
      <div className="rounded-xl border border-slate-700 bg-slate-900 p-5"><p className="text-xs text-slate-400">Recorded transactions</p>
        <p className="mt-2 text-2xl font-bold">{summary?.recorded_trades ?? 0}</p></div>
    </div>

    {market?.alerts && <div className="rounded-2xl border border-slate-700 bg-slate-900 p-5">
      <h2 className="text-xl font-semibold">Review alerts — not automatic sell signals</h2>
      <div className="mt-3 grid gap-3 md:grid-cols-2">{market.alerts.map(alert => <div key={alert.symbol}
        className={`rounded-xl border p-4 ${alert.status === 'review_exit_rules' ? 'border-amber-600 bg-amber-950/20' : 'border-slate-700 bg-slate-950'}`}>
        <div className="flex items-center justify-between"><strong>{alert.symbol}</strong>
          <span className="text-sm">{alert.status === 'review_exit_rules' ? '⚠ Reassess' : alert.status === 'data_unavailable' ? 'Data unavailable' : 'No rule triggered'}</span></div>
        {alert.reasons.map(reason => <p key={reason} className="mt-2 text-xs text-slate-300">{reason}</p>)}
      </div>)}</div>
      <p className="mt-3 text-xs text-slate-400">{market.alert_explanation}</p>
    </div>}

    <div className="grid gap-5 lg:grid-cols-2">
      <div className="rounded-2xl border border-slate-700 bg-slate-900 p-5">
        <h2 className="text-xl font-semibold">Your holdings</h2>
        {!values?.length && <p className="mt-3 text-sm text-slate-400">No purchases recorded yet. Use the form to add your first one.</p>}
        <div className="mt-4 space-y-4">{values?.map(row => <div key={row.symbol} className="rounded-xl bg-slate-950 p-4">
          <div className="flex items-center justify-between"><strong>{row.symbol}</strong><span className="font-semibold">{row.estimated_value_usd ? currency(row.estimated_value_usd) : 'Price not checked'}</span></div>
          <p className="mt-1 text-xs text-slate-400">{row.shares} shares · Recorded cost {currency(row.cost_basis_usd)}</p>
          {row.estimated_value_usd && <><div className="mt-3 h-3 rounded-full bg-slate-800"><div className="h-full rounded-full bg-emerald-400" style={{width: `${sum > 0 ? Math.max(0, Math.min(100, 100 * Number(row.estimated_value_usd) / sum)) : 0}%`}} /></div>
            <p className="mt-2 text-xs text-slate-300">{row.unrealized_gain_pct !== null ? `${row.unrealized_gain_pct > 0 ? '+' : ''}${row.unrealized_gain_pct}%` : 'Unavailable'} change from recorded cost · last price {row.last_price_date}</p></>}
          <Link className="mt-2 inline-block text-xs text-emerald-300 underline" to={`/history?symbol=${encodeURIComponent(row.symbol)}`}>See historical price chart</Link>
        </div>)}</div>
      </div>
      <form onSubmit={record} className="space-y-4 rounded-2xl border border-slate-700 bg-slate-900 p-5">
        <h2 className="text-xl font-semibold">Record a purchase or sale</h2>
        <div className="flex flex-wrap gap-2">{(['buy','sell','split'] as const).map(choice => <button key={choice} type="button" onClick={() => setAction(choice)}
          aria-pressed={action === choice} className={`rounded-full border px-4 py-2 text-sm ${action === choice ? 'border-emerald-400 bg-emerald-900' : 'border-slate-700'}`}>
            {choice === 'buy' ? 'Bought' : choice === 'sell' ? 'Sold' : 'Share split / adjustment'}</button>)}</div>
        <div className="grid grid-cols-2 gap-3"><label className="text-sm">Stock ticker
          <input aria-label="Trade ticker" required maxLength={20} value={symbol} onChange={e => setSymbol(e.target.value)} placeholder="AAPL" className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 p-3" /></label>
          <label className="text-sm">Date
            <input aria-label="Trade date" type="date" max={today} required value={tradeDate} onChange={e => setTradeDate(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 p-3" /></label></div>
        {action === 'split' ? <label className="block text-sm">New shares per old share (e.g. 2 for a 2-for-1 split)
          <input aria-label="Share adjustment ratio" value={ratio} onChange={e => setRatio(e.target.value)} required className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 p-3" /></label> :
          <div className="grid gap-3 sm:grid-cols-3"><label className="text-sm">How many shares?
            <input aria-label="Trade shares" required inputMode="decimal" value={shares} onChange={e => setShares(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 p-3" /></label>
            <label className="text-sm">Price paid or received for each share ($)
              <input aria-label="Trade share price" required inputMode="decimal" value={price} onChange={e => setPrice(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 p-3" /></label>
            <label className="text-sm">Fees ($)
              <input aria-label="Trade fee" inputMode="decimal" value={fee} onChange={e => setFee(e.target.value)} className="mt-1 block w-full rounded-lg border border-slate-700 bg-slate-950 p-3" /></label></div>}
        <button type="submit" disabled={saving} className="w-full rounded-xl bg-emerald-700 px-4 py-3 font-semibold disabled:opacity-50">{saving ? 'Saving…' : 'Save this actual transaction'}</button>
        <p className="text-xs text-slate-400">Buying and selling here only saves a manual record. Nothing is traded. Recording splits adjusts share counts but not cash payouts or taxes.</p>
      </form>
    </div>
    <div className="rounded-xl border border-slate-700 bg-slate-900 p-5">
      <div className="flex flex-wrap items-center justify-between gap-3"><h2 className="text-xl font-semibold">Recent transaction history</h2>
        <button disabled={!portfolio?.trades.length || saving} onClick={undoLatest} type="button" className="rounded-lg border border-amber-700 px-4 py-2 text-sm text-amber-200 disabled:opacity-30">Undo most recent entry</button></div>
      <div className="mt-3 space-y-2">{portfolio?.trades.slice(-12).reverse().map(trade => <p key={trade.id} className="flex flex-wrap justify-between gap-2 border-b border-slate-800 py-2 text-sm">
        <span><strong>{trade.symbol}</strong> · {trade.action} · {trade.date}</span>
        <span className="text-slate-300">{trade.action === 'split' ? `${trade.ratio} new shares per share` : `${trade.shares} shares at ${currency(trade.price_usd ?? 0)}`}</span>
      </p>)}</div>
    </div>
    {error && <p role="alert" className="rounded-lg border border-rose-700 p-4 text-sm text-rose-200">{error}</p>}
    <p className="text-xs text-slate-400">{summary?.caveat}</p>
  </section>
}
