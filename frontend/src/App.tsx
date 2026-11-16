import { NavLink, Route, Routes } from 'react-router'
import MarketPanel from './features/market/MarketPanel'
import WatchlistPage from './features/watchlist/WatchlistPage'
import ScannerPage from './features/scanner/ScannerPage'
import BudgetPlannerPage from './features/research/BudgetPlannerPage'
import ResearchOverview from './features/research/ResearchOverview'
import PredictionLabPage from './features/research/PredictionLabPage'
import DecisionDeskPage from './features/research/DecisionDeskPage'

const navigation = [
  { path: '/', label: 'Dashboard' },
  { path: '/watchlist', label: "Stocks I'm Following" },
  { path: '/scanner', label: 'Find Opportunities' },
  { path: '/decisions', label: 'Research Decision Desk' },
  { path: '/planner', label: 'Investment Planner' },
  { path: '/portfolio', label: 'Portfolio' },
  { path: '/forecasts', label: 'Forecast Lab' },
]

interface PageProps {
  title: string
  description: string
}

function PlaceholderPage({ title, description }: PageProps) {
  return (
    <section className="rounded-2xl border border-slate-800 bg-slate-900 p-8">
      <p className="mb-3 text-sm font-medium text-emerald-400">Initial development</p>
      <h1 className="text-3xl font-bold text-white">{title}</h1>
      <p className="mt-4 max-w-2xl text-slate-400">{description}</p>
      <div className="mt-8 rounded-xl border border-slate-700 bg-slate-950 p-5">
        <p className="font-medium text-white">Data feeds not connected</p>
        <p className="mt-2 text-sm text-slate-400">
          This feature is not yet connected to the backend.
        </p>
      </div>
    </section>
  )
}

function DashboardPage() {
  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Dashboard</h1>
        <p className="mt-2 text-slate-400">Monitor incoming market data and its reliability.</p>
      </div>
      <ResearchOverview />
      <MarketPanel />
    </div>
  )
}

export default function App() {
  return (
    <div className="min-h-screen bg-slate-950 text-slate-100">
      <header className="border-b border-slate-800 bg-slate-900">
        <div className="mx-auto max-w-7xl px-6 py-6">
          <p className="text-2xl font-bold tracking-tight">
            <span className="text-emerald-400">Stock</span>TradingWeb
          </p>
          <p className="mt-1 text-sm text-slate-400">Evidence-driven investment analysis</p>
        </div>
      </header>
      <nav aria-label="Primary navigation" className="border-b border-slate-800">
        <div className="mx-auto flex max-w-7xl flex-wrap gap-2 px-6 py-4">
          {navigation.map((item) => (
            <NavLink key={item.path} to={item.path} end={item.path === '/'}
              className={({ isActive }) =>
                `rounded-lg px-4 py-2 text-sm font-medium transition-colors ${
                  isActive
                    ? 'bg-emerald-600 text-white'
                    : 'text-slate-400 hover:bg-slate-800 hover:text-white'
                }`
              }>
              {item.label}
            </NavLink>
          ))}
        </div>
      </nav>
      <main className="mx-auto max-w-7xl px-6 py-10">
        <Routes>
          <Route path="/" element={<DashboardPage />} />
          <Route path="/watchlist" element={<WatchlistPage />} />
          <Route path="/scanner" element={<ScannerPage />} />
          <Route path="/planner" element={<BudgetPlannerPage />} />
          <Route path="/decisions" element={<DecisionDeskPage />} />
          <Route path="/portfolio" element={<PlaceholderPage title="Portfolio"
            description="Track positions, transactions, gains, and portfolio risk." />} />
          <Route path="/forecasts" element={<PredictionLabPage />} />
          <Route path="*" element={<PlaceholderPage title="Page Not Found"
            description="This page does not exist." />} />
        </Routes>
      </main>
      <footer className="mx-auto max-w-7xl px-6 pb-8 text-xs text-slate-500">
        Research software in development. No investment recommendations are currently available.
      </footer>
    </div>
  )
}
