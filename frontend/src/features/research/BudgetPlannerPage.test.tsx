import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import BudgetPlannerPage from './BudgetPlannerPage'

const sample = {
  budget_usd: '100.00', style: 'balanced', experimental_opt_in: false,
  horizon: 'long', max_loss_usd: null, modeled_risky_principal_usd: '65.00',
  loss_cap_binding: false,
  planning_explanations: ['Five-plus years is an illustration.'],
  stress_scenarios: [
    { decline_percent: 10, loss_usd: '6.50', remaining_budget_usd: '93.50' },
    { decline_percent: 30, loss_usd: '19.50', remaining_budget_usd: '80.50' },
    { decline_percent: 100, loss_usd: '65.00', remaining_budget_usd: '35.00' },
  ],
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
    expect(screen.getByText(/Educational scenarios only/)).toBeTruthy()
  })

  it('posts the budget and selected style with experimental picks off by default', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      budget_usd: '100.00', style: 'balanced', allow_experimental_stocks: false,
      horizon: 'long', max_loss_usd: null,
    })
    await waitFor(() => expect(screen.getByText('Cash / unallocated budget')).toBeTruthy())
    expect(screen.getByText(/No fresh individual-stock shortlist/)).toBeTruthy()
  })

  it('does not request impossible or fractional-cent budgets', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Investment amount in dollars'), { target: { value: '100.001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submits the selected horizon and affordable-loss ceiling', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('When might you need this money?'), { target: { value: 'medium' } })
    fireEvent.change(screen.getByLabelText('Maximum affordable loss in dollars'), { target: { value: '25.00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      budget_usd: '100.00', style: 'balanced', allow_experimental_stocks: false,
      horizon: 'medium', max_loss_usd: '25.00',
    })
  })

  it('rejects an affordable-loss number above the budget without calling the API', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Maximum affordable loss in dollars'), { target: { value: '100.01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects fractional-cent affordable loss without calling the API', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Maximum affordable loss in dollars'), { target: { value: '25.001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('clears a previous plan whenever the planning inputs change', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Why these amounts?')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('When might you need this money?'), { target: { value: 'short' } })
    expect(screen.queryByText('Why these amounts?')).toBeNull()
  })

  it('explains losses under the stress scenarios', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Hypothetical downside scenarios')).toBeTruthy())
    expect(screen.getByText('Risky assets fall 100%')).toBeTruthy()
    expect(screen.getByText('No personal affordable-loss cap was provided.', { exact: false })).toBeTruthy()
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
