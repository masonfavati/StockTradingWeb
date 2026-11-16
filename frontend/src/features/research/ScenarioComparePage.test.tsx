import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import ScenarioComparePage from './ScenarioComparePage'

function plan(body: { style: string; horizon: string; budget_usd: string;
  max_loss_usd: string | null; allow_experimental_stocks: boolean }) {
  const dollars = Number(body.budget_usd)
  const invested = body.horizon === 'short' ? 0 : Math.round(dollars *
    (body.style === 'cautious' ? 0.6 : body.style === 'balanced' ? 0.65 : 0.7) * 100) / 100
  const cash = Math.round((dollars - invested) * 100) / 100
  const money = (v: number) => v.toFixed(2)
  const thirty = Math.round(invested * 30) / 100
  return {
    budget_usd: body.budget_usd, horizon: body.horizon, style: body.style,
    max_loss_usd: body.max_loss_usd, experimental_opt_in: body.allow_experimental_stocks,
    scan_usable_for_ideas: false, source_session: null, source_kind: null,
    loss_cap_binding: false, planning_explanations: ['Illustrative allocation only.'],
    warnings: ['No trades occur.'],
    stress_scenarios: [{ decline_percent: 30, loss_usd: money(thirty),
      remaining_budget_usd: money(dollars - thirty) }],
    allocation: [
      { category: 'diversified_core_example', amount_usd: money(invested),
        symbol: 'SPY', name: 'Core ETF example', reason: 'Illustrative core' },
      { category: 'cash', amount_usd: money(cash), symbol: null,
        name: 'Cash', reason: 'Preserved cash' },
    ],
    total_invested_example_usd: money(invested), unallocated_cash_usd: money(cash),
  }
}

describe('Budget Comparison Workspace', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) => ({
      ok: true, json: async () => plan(JSON.parse(init.body as string)),
    }))
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

  it('is opt-in and does not query markets on page load', () => {
    render(<MemoryRouter><ScenarioComparePage /></MemoryRouter>)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText(/More money invested is not automatically a better choice/)).toBeTruthy()
  })
  it('shows three consistent dollar outcomes and links to the full planner', async () => {
    render(<MemoryRouter><ScenarioComparePage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Compare three allocation styles' }))
    await waitFor(() => expect(screen.getByLabelText('Completed comparison')).toBeTruthy())
    expect(fetchMock).toHaveBeenCalledTimes(3)
    expect(screen.getByLabelText('Cautious comparison')).toBeTruthy()
    expect(screen.getByLabelText('Balanced comparison')).toBeTruthy()
    expect(screen.getByLabelText('Growth-oriented comparison')).toBeTruthy()
    expect(screen.getByText(/\$100\.00 total in every column/)).toBeTruthy()
    expect(screen.getAllByText('Retained cash:', { exact: false })).toHaveLength(3)
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string))
    expect(bodies.map(row => row.style)).toEqual(['cautious', 'balanced', 'growth'])
    expect(bodies.every(row => row.allow_experimental_stocks === false)).toBe(true)
    expect(screen.getAllByText('Inspect this style in the full planner')).toHaveLength(3)
  })
  it('validates input locally and invalidates stale comparisons on input change', async () => {
    render(<MemoryRouter><ScenarioComparePage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Comparison budget'), { target: { value: '100.001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Compare three allocation styles' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
    fireEvent.change(screen.getByLabelText('Comparison budget'), { target: { value: '100.00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Compare three allocation styles' }))
    await waitFor(() => expect(screen.getByLabelText('Completed comparison')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Comparison horizon'), { target: { value: 'medium' } })
    expect(screen.queryByLabelText('Completed comparison')).toBeNull()
  })
  it('requires selected research gates for experimental comparison', async () => {
    render(<MemoryRouter><ScenarioComparePage /></MemoryRouter>)
    fireEvent.click(screen.getByLabelText(/Include experimental individual-stock research ideas/))
    fireEvent.click(screen.getByRole('button', { name: 'Compare three allocation styles' }))
    await waitFor(() => expect(screen.getByLabelText('Completed comparison')).toBeTruthy())
    const bodies = fetchMock.mock.calls.map(([, init]) => JSON.parse((init as RequestInit).body as string))
    expect(bodies).toHaveLength(3)
    expect(bodies.every(row => row.allow_experimental_stocks && row.require_prediction &&
      row.require_sec_identity && row.require_sec_industry && row.require_historical_comovement)).toBe(true)
  })
  it('does not show partial results if a planner request fails', async () => {
    fetchMock.mockImplementation(async (_url: string, init: RequestInit) => {
      const body = JSON.parse(init.body as string)
      if (body.style === 'growth') return { ok: false }
      return { ok: true, json: async () => plan(body) }
    })
    render(<MemoryRouter><ScenarioComparePage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Compare three allocation styles' }))
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.queryByLabelText('Completed comparison')).toBeNull()
  })
})
