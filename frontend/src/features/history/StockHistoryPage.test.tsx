import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import StockHistoryPage from './StockHistoryPage'

const response = {
  symbol: 'AAPL', period: '1y', provider: 'alpaca', feed: 'sip', adjustment: 'all',
  fetched_at_utc: '2026-11-15T20:00:00+00:00',
  first_session: '2026-11-11', last_session: '2026-11-13', session_count: 2,
  last_adjusted_close_usd: 102, period_change_pct: 2,
  historical_insights: {
    highest_price_usd: 102, highest_date: '2026-11-13',
    lowest_price_usd: 100, lowest_date: '2026-11-11',
    largest_drop_from_previous_high_pct: 0,
    drop_high_date: '2026-11-11', drop_low_date: '2026-11-11',
    average_change_between_recorded_days_pct: 2,
    up_days: 1, down_days: 0, flat_days: 0,
    spy_change_pct: null, difference_vs_spy_percentage_points: null,
  },
  bars: [
    { session_date: '2026-11-11', adjusted_close_usd: 100, normalized_index: 100 },
    { session_date: '2026-11-13', adjusted_close_usd: 102, normalized_index: 102 },
  ], spy_benchmark: [], benchmark_available: false, warning: null,
  caveat: 'Not a trading quote.', price_forecast: null,
  forecast_status: 'no_validated_price_forecast',
}

const renderPage = (path = '/history?symbol=AAPL&signal=2026-11-13') =>
  render(<MemoryRouter initialEntries={[path]}><StockHistoryPage /></MemoryRouter>)

describe('Stock History page', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => response })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals() })

  it('fetches independent prices for a deep linked ticker without starting a scan', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('Last recorded daily price (adjusted)')).toBeTruthy())
    expect(fetchMock.mock.calls[0][0]).toContain('/api/research/stock-history/AAPL?')
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(screen.getByRole('img', { name: /AAPL historical/ })).toBeTruthy()
    expect(screen.getByText(/No future price line or invented confidence interval/)).toBeTruthy()
  })

  it('explains important price movements without suggesting a forecast', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByText('What happened during these dates?')).toBeTruthy())
    expect(screen.getByText('Highest recorded price')).toBeTruthy()
    expect(screen.getByText('Biggest fall after an earlier high')).toBeTruthy()
    expect(screen.getByText(/Not reliably yet/)).toBeTruthy()
  })

  it('switches to another period without a market scan', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('img', { name: /AAPL historical/ })).toBeTruthy())
    fireEvent.click(screen.getByRole('button', { name: '5 years' }))
    await waitFor(() => expect(fetchMock.mock.calls.some(([url]) => String(url).includes('period=5y'))).toBe(true))
  })

  it('validates ticker before attempting to fetch it', async () => {
    renderPage()
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    fireEvent.change(screen.getByLabelText('Stock symbol (ticker)'), { target: { value: 'ABC & DELETE' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show history' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('treats a provider failure as unavailable instead of displaying fabricated data', async () => {
    fetchMock.mockRejectedValue(new Error('Historical prices are unavailable.'))
    renderPage()
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.queryByRole('img')).toBeNull()
  })

  it('provides a keyboard-operable session inspector', async () => {
    renderPage()
    await waitFor(() => expect(screen.getByRole('img', { name: /AAPL historical/ })).toBeTruthy())
    const slider = screen.getByLabelText('Inspect historical session')
    fireEvent.change(slider, { target: { value: '0' } })
    expect(screen.getByText(/2026-11-11 · AAPL past price/)).toBeTruthy()
  })
})
