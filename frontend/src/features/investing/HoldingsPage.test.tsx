import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import HoldingsPage from './HoldingsPage'

const empty = {summary: {
  holdings: [], recorded_trades: 0, realized_gain_usd: '0.00',
  estimated_portfolio_value_usd: '0.00', valuation_complete: true,
  caveat: 'Manual records only.',
}, trades: []}
const fetchMock = vi.fn()
beforeEach(() => {fetchMock.mockReset(); vi.stubGlobal('fetch', fetchMock)})
afterEach(() => vi.unstubAllGlobals())

describe('Manual holdings', () => {
  it('loads holdings without trading or fetching fresh market data', async () => {
    fetchMock.mockResolvedValue({ok: true, json: async () => empty})
    render(<MemoryRouter><HoldingsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No purchases recorded yet/)).toBeTruthy())
    expect(fetchMock).toHaveBeenCalledTimes(1)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/investing/portfolio')
  })

  it('records the user-specified purchase without connecting to a broker', async () => {
    fetchMock.mockImplementation(async (url: string) => ({ok: true,
      json: async () => url.endsWith('/trades') ? {saved: true} : empty,
    }))
    render(<MemoryRouter><HoldingsPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No purchases recorded yet/)).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Trade ticker'), {target: {value: 'AAPL'}})
    fireEvent.change(screen.getByLabelText('Trade share price'), {target: {value: '110.00'}})
    fireEvent.click(screen.getByRole('button', {name: 'Save this actual transaction'}))
    await waitFor(() => expect(fetchMock.mock.calls.some(c => c[0] === '/api/investing/portfolio/trades')).toBe(true))
    const call = fetchMock.mock.calls.find(c => c[0] === '/api/investing/portfolio/trades')
    expect(JSON.parse(call![1].body as string)).toMatchObject({symbol: 'AAPL', action: 'buy', price_usd: '110.00'})
  })
})
