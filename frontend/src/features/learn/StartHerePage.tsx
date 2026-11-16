import { Link } from 'react-router'
import BeginnerHelp from './BeginnerHelp'

const steps = [
  { heading: '1. Pick a company', body: 'Use Stocks I’m Following to look up a company by name. Saving a company does not buy anything.', path: '/watchlist', action: 'Find a company' },
  { heading: '2. See what really happened', body: 'Open Stock Price History to see years of past prices, gains, and drops. You do not need to run a market search first.', path: '/history', action: 'See price history' },
  { heading: '3. Explore possible ideas', body: 'Find Opportunities searches historical data for stocks worth researching. A match is not a forecast or a recommendation.', path: '/scanner', action: 'Explore stocks' },
  { heading: '4. Try a pretend budget', body: 'Use Plan My Budget to see example amounts invested and left as cash. You decide your time frame and how much you can afford to lose.', path: '/planner', action: 'Try an example' },
]

export default function StartHerePage() {
  return <section className="space-y-6" aria-label="Beginner guide to the stock market">
    <div className="rounded-2xl border border-slate-800 bg-slate-900 p-7">
      <p className="text-sm font-semibold text-emerald-400">New to investing? Start here.</p>
      <h1 className="mt-2 text-3xl font-bold">Understand stocks without the jargon</h1>
      <p className="mt-3 max-w-3xl text-slate-300">A stock is a small piece of ownership in a company. Its price can go up or down, and you could lose your money. This website helps you explore information; it does not buy stocks or promise which ones will succeed.</p>
      <p className="mt-3 text-sm text-amber-200">There are no verified buy recommendations here yet. Past performance and model experiments do not guarantee future results.</p>
    </div>
    <div className="grid gap-4 md:grid-cols-2">
      {steps.map(step => <article key={step.heading} className="rounded-xl border border-slate-800 bg-slate-900 p-5">
        <h2 className="text-lg font-semibold">{step.heading}</h2>
        <p className="mt-2 text-sm leading-relaxed text-slate-300">{step.body}</p>
        <Link to={step.path} className="mt-4 inline-block text-sm font-semibold text-emerald-300 underline">{step.action}</Link>
      </article>)}
    </div>
    <div className="rounded-xl border border-slate-800 bg-slate-900 p-5">
      <h2 className="text-xl font-semibold">Three things to remember</h2>
      <ol className="mt-3 list-decimal space-y-2 pl-5 text-sm text-slate-300">
        <li>Looking up a stock, following it, or making a pretend budget does not place a trade.</li>
        <li>A stock that went up in the past can fall tomorrow. A number on a chart is not a promise.</li>
        <li>Money marked as <strong>cash</strong> is simply the part of your pretend budget the app would leave uninvested.</li>
      </ol>
    </div>
    <BeginnerHelp title="See the beginner stock-market dictionary" words={[
      'stock', 'ticker', 'fund', 'spy', 'cash', 'adjusted', 'change', 'daily', 'drop',
      'index', 'risk', 'correlation', 'sec', 'sic', 'scan', 'prediction', 'forecast', 'loss',
    ]} />
  </section>
}
