import BeginnerHelp from '../learn/BeginnerHelp'
import { useRef, useState, type FormEvent } from 'react'
import { Link, useSearchParams } from 'react-router'
import {
  calculateBudgetPlan,
  type BudgetPlan,
  type InvestmentHorizon,
  type PlanStyle,
} from './researchApi'
import { explainRetainedCash } from './allocationExplanation'
import { readPlannerQuery } from './scenarioComparison'
import { historyLink } from '../history/historyApi'

const qualityLabels: Record<string, string> = {
  unverified_share_type: 'Not enough evidence of ordinary shares',
  duplicate_ticker: 'Duplicate ticker',
  outdated_session: 'Not from the latest completed session',
  missing_or_invalid_metrics: 'Missing or invalid historical risk/liquidity data',
  below_price_floor: 'Below historical adjusted-price threshold',
  below_liquidity_screen: 'Below approximate historical trading-volume threshold',
  above_volatility_screen: 'Volatility exceeds research threshold',
  outside_drawdown_screen: 'Recent drawdown outside research threshold',
  repeated_apparent_issuer: 'Possible duplicate company/share class',
  passed_not_selected: 'Passed screens; excluded by two-stock concentration limit',
}

function dollars(value: string): string {
  return new Intl.NumberFormat('en-US', { style: 'currency', currency: 'USD' }).format(Number(value))
}

export default function BudgetPlannerPage() {
  const [query] = useSearchParams()
  const [defaults] = useState(() => readPlannerQuery(query))
  const [budget, setBudget] = useState(defaults.budget)
  const [style, setStyle] = useState<PlanStyle>(defaults.style)
  const [horizon, setHorizon] = useState<InvestmentHorizon>(defaults.horizon)
  const [maxLoss, setMaxLoss] = useState(defaults.maxLoss)
  const [experimental, setExperimental] = useState(defaults.experimental)
  const [requireComovement, setRequireComovement] = useState(defaults.comovement)
  const [requireSecIdentity, setRequireSecIdentity] = useState(defaults.secIdentity)
  const [requireSecIndustry, setRequireSecIndustry] = useState(defaults.secIndustry)
  const [requirePrediction, setRequirePrediction] = useState(defaults.prediction)
  const [plan, setPlan] = useState<BudgetPlan | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [pending, setPending] = useState(false)
  const requestSerial = useRef(0)

  function invalidatePlan() {
    requestSerial.current += 1
    setPlan(null)
    setError(null)
    setPending(false)
  }

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault()
    const serial = ++requestSerial.current
    setError(null)
    setPlan(null)
    if (!/^\d+(\.\d{1,2})?$/.test(budget) || Number(budget) <= 0 || Number(budget) > 1_000_000) {
      setError('Enter an amount from $0.01 to $1,000,000, using at most two decimal places.')
      return
    }
    if (maxLoss !== '' && (!/^\d+(\.\d{1,2})?$/.test(maxLoss) || Number(maxLoss) > Number(budget))) {
      setError('The maximum affordable loss must be between $0.00 and your investment amount, in whole cents.')
      return
    }
    setPending(true)
    try {
      const calculated = await calculateBudgetPlan(
        budget, style, experimental, horizon, maxLoss || null,
        experimental && requireComovement, experimental && requireSecIdentity,
        experimental && requireSecIndustry, experimental && requirePrediction,
      )
      if (requestSerial.current === serial) setPlan(calculated)
    } catch (caught) {
      if (requestSerial.current === serial) {
        setError(caught instanceof Error ? caught.message : 'Unable to calculate a plan.')
      }
    } finally {
      if (requestSerial.current === serial) setPending(false)
    }
  }

  return <section className="space-y-6" aria-label="Investment budget planner">
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:p-8">
      <p className="text-sm font-semibold text-emerald-400">Research and plan</p>
      <h1 className="mt-2 text-3xl font-bold">Plan how a budget might be divided</h1>
      <p className="mt-3 max-w-3xl text-slate-300">
        Enter how much money you are thinking about, when you might need it, and how much
        you could afford to lose. See a pretend split between investments and cash.
      </p>
      <Link to="/compare" className="mt-3 inline-block text-sm text-emerald-400 underline">Compare Cautious, Balanced, and Growth budgets side by side</Link>
      <p className="mt-3 text-sm text-amber-200">
        Educational scenarios only—not instructions to buy. The app has not yet proven
        that its stock-search ideas predict future profits.
      </p>
    </div>

    <form className="grid gap-5 rounded-2xl border border-slate-800 bg-slate-900 p-6 sm:grid-cols-2" onSubmit={(e) => { void submit(e) }}>
      <div>
        <label htmlFor="investment-budget" className="block text-sm font-medium">Amount you intend to invest</label>
        <div className="mt-2 flex items-center rounded-lg border border-slate-700 bg-slate-950 px-3">
          <span className="text-slate-400">$</span>
          <input id="investment-budget" aria-label="Investment amount in dollars" value={budget}
            onChange={(event) => { setBudget(event.target.value); invalidatePlan() }} inputMode="decimal"
            className="w-full bg-transparent px-2 py-3 text-white outline-none" placeholder="100.00" />
        </div>
      </div>
      <div>
        <label htmlFor="investment-style" className="block text-sm font-medium">Illustrative allocation style</label>
        <select id="investment-style" value={style} onChange={(event) => { setStyle(event.target.value as PlanStyle); invalidatePlan() }}
          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white">
          <option value="cautious">Cautious — less stock exposure</option>
          <option value="balanced">Balanced — diversified core</option>
          <option value="growth">Growth-oriented — more stock exposure</option>
        </select>
      </div>
      <div>
        <label htmlFor="investment-horizon" className="block text-sm font-medium">When might you need this money?</label>
        <select id="investment-horizon" value={horizon} onChange={(event) => { setHorizon(event.target.value as InvestmentHorizon); invalidatePlan() }}
          className="mt-2 w-full rounded-lg border border-slate-700 bg-slate-950 px-3 py-3 text-white">
          <option value="short">Within 1 year</option>
          <option value="medium">In 1–5 years</option>
          <option value="long">In 5+ years (example default)</option>
        </select>
        <p className="mt-2 text-xs text-slate-400">If you need the money sooner, the example puts less into stocks.</p>
      </div>
      <div>
        <label htmlFor="maximum-loss" className="block text-sm font-medium">Maximum you could afford to lose (optional)</label>
        <div className="mt-2 flex items-center rounded-lg border border-slate-700 bg-slate-950 px-3">
          <span className="text-slate-400">$</span>
          <input id="maximum-loss" aria-label="Maximum affordable loss in dollars" value={maxLoss}
            onChange={(event) => { setMaxLoss(event.target.value); invalidatePlan() }} inputMode="decimal"
            className="w-full bg-transparent px-2 py-3 text-white outline-none" placeholder="e.g. 25.00" />
        </div>
        <p className="mt-2 text-xs text-slate-400">
          We use this amount to limit how much of the example budget goes into stocks. It cannot guarantee how much you might lose.
        </p>
      </div>
      <label className="flex items-start gap-3 text-sm text-slate-200 sm:col-span-2">
        <input type="checkbox" className="mt-1 accent-emerald-500" checked={experimental}
          onChange={(event) => { setExperimental(event.target.checked); invalidatePlan() }} />
        <span>Also consider individual stocks found by the market search (experimental).
          No single stock gets more than 10% of your example budget. These are not suggestions to buy.</span>
      </label>
      {experimental && <label className="flex items-start gap-3 text-sm text-slate-200 sm:col-span-2">
        <input type="checkbox" className="mt-1 accent-emerald-500" checked={requireSecIdentity || requireSecIndustry}
          disabled={requireSecIndustry}
          aria-label="Require SEC filer cross-reference"
          onChange={(event) => { setRequireSecIdentity(event.target.checked); invalidatePlan() }} />
        <span>Check each company’s identity using official government records.
          If the match is missing or uncertain, leave that money as cash. Official data must first be imported on the server.
          This does not prove the stock is a good investment.</span>
      </label>}
      {experimental && <label className="flex items-start gap-3 text-sm text-slate-200 sm:col-span-2">
        <input type="checkbox" className="mt-1 accent-emerald-500" checked={requireSecIndustry}
          aria-label="Require SEC SIC industry evidence"
          onChange={(event) => { setRequireSecIndustry(event.target.checked); invalidatePlan() }} />
        <span>Check each company’s reported type of business.
          The app avoids putting experimental money into two stocks with the same government industry code.
          Missing or old company information means those dollars stay as cash. The server needs imported SEC records.</span>
      </label>}
      {experimental && <label className="flex items-start gap-3 text-sm text-slate-200 sm:col-span-2">
        <input type="checkbox" className="mt-1 accent-emerald-500" checked={requireComovement}
          aria-label="Require historical co-movement evidence"
          onChange={(event) => { setRequireComovement(event.target.checked); invalidatePlan() }} />
        <span>Check whether the individual stocks tended to rise and fall together.
          If the history is missing or two stocks moved too similarly, leave the affected money as cash.
          This can request some additional historical prices.</span>
      </label>}
      {experimental && <label className="flex items-start gap-3 text-sm text-slate-200 sm:col-span-2">
        <input type="checkbox" className="mt-1 accent-emerald-500" checked={requirePrediction}
          aria-label="Require prospective prediction evidence"
          onChange={(event) => { setRequirePrediction(event.target.checked); invalidatePlan() }} />
        <span>Only include individual stocks if the experimental prediction has passed enough real-world tests.
          Otherwise leave that money as cash. The prediction compares a stock with SPY; it does not
          predict a share price or guarantee a profit.</span>
      </label>}
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
            'No fresh individual-stock shortlist is used for this scenario. '}
          No orders are placed.
        </p>
        <div className="mt-4 rounded-xl border border-slate-700 bg-slate-950 p-4">
          <h3 className="font-semibold">Why these amounts?</h3>
          <ul className="mt-2 list-disc space-y-2 pl-5 text-sm text-slate-300">
            {plan.planning_explanations.map((explanation) => <li key={explanation}>{explanation}</li>)}
          </ul>
          <p className="mt-3 text-sm text-amber-200">
            Example amount exposed to stock-price changes: {dollars(plan.modeled_risky_principal_usd)}.
            {plan.max_loss_usd !== null
              ? ` You entered ${dollars(plan.max_loss_usd)} as the most you could afford to lose.`
              : ' No personal affordable-loss cap was provided.'}
          </p>
          {plan.loss_cap_binding && <p className="mt-2 text-sm text-emerald-300">
            The dollar-loss limit reduced this scenario's stock exposure.
          </p>}
        </div>
        {plan.experimental_opt_in && <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950 p-4">
          <h3 className="font-semibold">Individual-stock research quality checks</h3>
          {plan.quality_review?.applied ? <>
            <p className="mt-2 text-sm text-slate-300">
              Reviewed {plan.quality_review.screened_count} ranked shortlist candidates; selected{' '}
              {plan.quality_review.selected_count} for possible experimental slices.
              This is not a review of every security in the market.
            </p>
            <details className="mt-3 text-xs text-slate-400"><summary className="cursor-pointer text-emerald-300">Show the technical screening thresholds</summary><p className="mt-2">
              Historical adjusted price ≥ {dollars(String(plan.quality_review.thresholds.min_adjusted_close_usd))};
              {' '}approximate recent daily dollar volume ≥ {dollars(String(plan.quality_review.thresholds.min_approx_daily_dollar_volume_usd))};
              {' '}annualized volatility ≤ {plan.quality_review.thresholds.max_annualized_volatility_pct}%;
              {' '}60-session drawdown ≥ {plan.quality_review.thresholds.min_60d_drawdown_pct}%.
              At most {plan.quality_review.thresholds.max_individual_stocks} apparent distinct issuers.
            </p></details>
            {Object.entries(plan.quality_review.excluded_counts).length > 0 && <div className="mt-3">
              <p className="text-sm font-semibold">Why shortlist candidates were excluded</p>
              <ul className="mt-2 list-disc space-y-1 pl-5 text-xs text-slate-300">
                {Object.entries(plan.quality_review.excluded_counts).map(([key, count]) =>
                  <li key={key}>{qualityLabels[key] ?? key}: {count}</li>)}
              </ul>
            </div>}
            <p className="mt-3 text-xs text-amber-200">{plan.quality_review.caveat}</p>
          </> : <p className="mt-2 text-sm text-amber-200">
            No quality screening was applied because the optional stock allocation was not available,
            the historical shortlist was not recent enough, or the risk budget was too small.
          </p>}
        </div>}
        {plan.experimental_opt_in && plan.sec_identity_required && plan.sec_identity_review &&
          <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950 p-4">
            <h3 className="font-semibold">Official company identity check</h3>
            <p className="mt-2 text-sm text-slate-300">
              Status: {plan.sec_identity_review.status}; approved {plan.sec_identity_review.approved_symbols.length}
              {' '}of {plan.sec_identity_review.requested_symbols.length} proposed stock(s).
              {plan.sec_identity_review.imported_at_utc &&
                ` Reference imported ${plan.sec_identity_review.imported_at_utc}.`}
            </p>
            {plan.sec_identity_review.matches.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {plan.sec_identity_review.matches.map(item => <li key={item.symbol}>
                {item.symbol}: SEC filer {item.sec_filer_name} (CIK {item.cik}, {item.sec_exchange}).
              </li>)}
            </ul>}
            {plan.sec_identity_review.excluded.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-200">
              {plan.sec_identity_review.excluded.map(item => <li key={item.symbol}>
                {item.symbol}: {item.reason.replace(/_/g, ' ')}; proposed dollars remain cash.
              </li>)}
            </ul>}
            <p className="mt-3 text-xs text-amber-200">{plan.sec_identity_review.caveat}</p>
            <a className="mt-2 inline-block text-sm text-emerald-400 underline" target="_blank"
              rel="noopener noreferrer" href="https://www.sec.gov/file/company-tickers-exchange">
              SEC official ticker-reference source
            </a>
          </div>}
        {plan.experimental_opt_in && plan.sec_industry_required && plan.sec_industry_review &&
          <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950 p-4">
            <h3 className="font-semibold">Reported type of business check</h3>
            <p className="mt-2 text-sm text-slate-300">
              Status: {plan.sec_industry_review.status}; approved {plan.sec_industry_review.approved_symbols.length}
              {' '}of {plan.sec_industry_review.requested_symbols.length} proposed stock(s).
              {plan.sec_industry_review.imported_at_utc &&
                ` Metadata imported ${plan.sec_industry_review.imported_at_utc}.`}
            </p>
            {plan.sec_industry_review.matches.length > 0 && <ul className="mt-2 list-disc space-y-1 pl-5 text-sm text-slate-300">
              {plan.sec_industry_review.matches.map(item => <li key={item.symbol}>
                {item.symbol}: SEC SIC {item.sic} — {item.sic_description} (CIK {item.cik}).
              </li>)}
            </ul>}
            {plan.sec_industry_review.excluded.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-200">
              {plan.sec_industry_review.excluded.map(item => <li key={item.symbol}>
                {item.symbol}: {item.reason.replace(/_/g, ' ')}; proposed dollars remain cash.
              </li>)}
            </ul>}
            <p className="mt-3 text-xs text-amber-200">{plan.sec_industry_review.caveat}</p>
            <a className="mt-2 inline-block text-sm text-emerald-400 underline" target="_blank"
              rel="noopener noreferrer"
              href="https://www.sec.gov/search-filings/edgar-application-programming-interfaces">
              SEC official submissions data documentation
            </a>
          </div>}
        {plan.experimental_opt_in && plan.prediction_required && plan.prediction_review &&
          <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950 p-4">
            <h3 className="font-semibold">Did the predictions pass real-world tests?</h3>
            <p className="mt-2 text-sm text-slate-300">
              Status: {plan.prediction_review.status.replace(/_/g, ' ')}.
              {' '}Approved {plan.prediction_review.approved_symbols.length} stock(s).
              {' '}Unapproved experimental dollars remain cash.
            </p>
            {plan.prediction_review.scores.length > 0 && <ul className="mt-3 space-y-2 text-sm text-slate-300">
              {plan.prediction_review.scores.map(row => <li key={row.symbol}>
                {row.symbol}: estimated chance of doing better than SPY{' '}
                {(row.estimated_probability_beating_spy * 100).toFixed(1)}%,
                simple historical comparison {(row.training_prior * 100).toFixed(1)}%.
              </li>)}
            </ul>}
            {plan.prediction_review.excluded.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-200">
              {plan.prediction_review.excluded.map(row => <li key={row.symbol}>
                {row.symbol}: {row.reason.replace(/_/g, ' ')}.
              </li>)}
            </ul>}
            <p className="mt-3 text-xs text-amber-200">{plan.prediction_review.caveat}</p>
            <Link to="/forecasts" className="mt-2 inline-block text-sm text-emerald-400 underline">
              See full walk-forward validation and limitations
            </Link>
          </div>}
        {plan.experimental_opt_in && plan.historical_comovement_required && plan.comovement_review &&
          <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950 p-4">
            <h3 className="font-semibold">Did these investments move together before?</h3>
            <p className="mt-2 text-sm text-slate-300">
              Check status: {plan.comovement_review.status.replace(/_/g, ' ')}.
              {' '}Approved {plan.comovement_review.approved_symbols.length} experimental stock(s).
              {' '}We require {plan.comovement_review.matched_sessions} common adjusted-price sessions.
            </p>
            {plan.comovement_review.spy_correlations.length > 0 && <p className="mt-2 text-sm text-slate-300">
              How closely each stock moved with SPY in the past (closer to 1 means more similar):{' '}
              {plan.comovement_review.spy_correlations.map(item =>
                `${item.symbol}: ${item.correlation.toFixed(2)}`).join('; ')}.
            </p>}
            {plan.comovement_review.pairwise_correlations.length > 0 && <p className="mt-2 text-sm text-slate-300">
              How closely the stocks moved with each other:{' '}
              {plan.comovement_review.pairwise_correlations.map(item =>
                `${item.symbol_a}/${item.symbol_b}: ${item.correlation.toFixed(2)}`).join('; ')}.
              Pairs with similarity score ≥ {plan.comovement_review.threshold_positive_correlation.toFixed(2)} are not both allocated.
            </p>}
            {plan.comovement_review.excluded.length > 0 && <ul className="mt-3 list-disc space-y-1 pl-5 text-sm text-amber-200">
              {plan.comovement_review.excluded.map(item => <li key={item.symbol}>
                {item.symbol}: {item.reason.replace(/_/g, ' ')}; its proposed money stays in cash.
              </li>)}
            </ul>}
            {plan.comovement_review.portfolio_annualized_historical_volatility_pct !== null && <p className="mt-3 text-sm text-slate-300">
              Past portfolio price swings (shown on a yearly scale):{' '}
              {plan.comovement_review.portfolio_annualized_historical_volatility_pct.toFixed(2)}%.
              {' '}Biggest observed drop during the last 60 recorded days:{' '}
              {plan.comovement_review.portfolio_historical_max_drawdown_pct?.toFixed(2) ?? 'unavailable'}%.
            </p>}
            <p className="mt-3 text-xs text-amber-200">{plan.comovement_review.caveat}</p>
          </div>}
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
              {item.symbol && <Link to={historyLink(item.symbol, plan.source_session)} className="mt-2 inline-block text-sm text-emerald-400 underline">View independent price history</Link>}
              {item.indicative_fractional_shares !== null && <p className="mt-2 text-xs text-amber-200">
                Approximately {item.indicative_fractional_shares} parts of a share using an older daily price
                of {dollars(item.historical_price_usd ?? '0')}; not a current executable quote.
              </p>}
            </article>
          ))}
        </div>
        <div className="mt-5 rounded-xl border border-slate-700 bg-slate-950 p-4">
          <h3 className="font-semibold">Why is this amount still cash?</h3>
          <p className="mt-2 text-sm text-slate-300">{dollars(plan.unallocated_cash_usd)} is retained rather than assigned to investments in this illustrative plan.</p>
          <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-300">
            {explainRetainedCash(plan).map(message => <li key={message}>{message}</li>)}
          </ul>
          <Link className="mt-3 inline-block text-sm text-emerald-400 underline" to="/decisions">Inspect the historical candidate evidence in the Decision Desk</Link>
        </div>
        <dl className="mt-5 grid grid-cols-2 gap-4 border-t border-slate-700 pt-4 text-sm">
          <div><dt className="text-slate-400">Example invested amount</dt>
            <dd className="mt-1 text-xl font-bold">{dollars(plan.total_invested_example_usd)}</dd></div>
          <div><dt className="text-slate-400">Retained as cash</dt>
            <dd className="mt-1 text-xl font-bold">{dollars(plan.unallocated_cash_usd)}</dd></div>
        </dl>
      </div>
      <div className="rounded-2xl border border-slate-800 bg-slate-900 p-6">
        <h2 className="text-xl font-semibold">Hypothetical downside scenarios</h2>
        <p className="mt-2 text-sm text-slate-400">
          These show what your example budget would look like after different stock-price drops.
          They are not predictions or maximum possible losses. Cash is assumed unchanged only to simplify the example.
        </p>
        <div className="mt-4 grid gap-3 sm:grid-cols-3">
          {plan.stress_scenarios.map((scenario) => <div key={scenario.decline_percent}
            className="rounded-xl border border-slate-700 bg-slate-950 p-4">
            <p className="text-sm text-slate-400">Stock investments fall {scenario.decline_percent}%</p>
            <p className="mt-2 text-xl font-semibold text-amber-200">−{dollars(scenario.loss_usd)}</p>
            <p className="mt-1 text-xs text-slate-400">Budget remaining: {dollars(scenario.remaining_budget_usd)}</p>
          </div>)}
        </div>
      </div>
      <div className="rounded-xl border border-slate-800 p-5">
        <h2 className="text-lg font-semibold">Before investing real money</h2>
        <ul className="mt-3 list-disc space-y-2 pl-5 text-sm text-slate-400">
          {plan.warnings.map((warning) => <li key={warning}>{warning}</li>)}
        </ul>
        <Link className="mt-4 inline-block text-emerald-400 hover:underline" to="/decisions">
          Explain every shortlisted candidate and its research evidence
        </Link>
      </div>
    </div>}
    <BeginnerHelp words={['stock', 'fund', 'spy', 'cash', 'loss', 'risk', 'sec', 'sic', 'correlation', 'prediction', 'forecast']} />
  </section>
}
