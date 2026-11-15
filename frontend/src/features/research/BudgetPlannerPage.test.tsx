import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import BudgetPlannerPage from './BudgetPlannerPage'

const sample = {
  budget_usd: '100.00', style: 'balanced', experimental_opt_in: false,
  scan_usable_for_ideas: false, source_session: null, source_kind: null,
  allocation: [
    { category: 'diversified_core_example', symbol: 'SPY', name: 'Broad U.S. market ETF example (SPY)',
      amount_usd: '65.00', percent_of_budget: 65, indicative_fractional_shares: null,
      historical_price_usd: null, reason: 'Example diversified fund.' },
    { category: 'cash', symbol: null, name: 'Cash / unallocated budget', amount_usd: '35.00',
      percent_of_budget: 35, indicative_fractional_shares: null, historical_price_usd: null, reason: 'Cash.' },
  ],
  total_invested_example_usd: '65.00', unallocated_cash_usd: '35.00',
  illustrative_equity_drop_30pct_usd: '19.50', warnings: ['No orders are created.'],
}

describe('BudgetPlannerPage', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => sample })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

  it('does not fetch or plan until the person asks', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText(/Educational example only/)).toBeTruthy()
  })

  it('posts the budget and selected style with experimental picks off by default', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      budget_usd: '100.00', style: 'balanced', allow_experimental_stocks: false,
    })
    await waitFor(() => expect(screen.getByText('Cash / unallocated budget')).toBeTruthy())
    expect(screen.getByText(/No fresh, verified-type stock shortlist/)).toBeTruthy()
  })

  it('does not request impossible or fractional-cent budgets', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Investment amount in dollars'), { target: { value: '100.001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('experimental picks require an explicit opt-in', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string).allow_experimental_stocks).toBe(true)
  })
})
