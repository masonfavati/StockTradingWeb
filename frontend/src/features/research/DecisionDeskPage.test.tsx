import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import DecisionDeskPage from './DecisionDeskPage'

const item = (symbol: string, passed: boolean) => ({
  rank: symbol === 'AAA' ? 1 : 2,
  symbol,
  name: `${symbol} Corporation Common Stock`,
  quality_passed: passed,
  quality_reason: passed ? null : 'below_price_floor',
  metrics: {
    adjusted_close: passed ? 20 : 2, return_20d_pct: 5.1,
    return_60d_pct: 15.0, annualized_volatility_pct: 30.0,
    drawdown_60d_pct: -10, approx_daily_dollar_volume: 12_000_000,
    research_score: 0.75,
  },
  sec_filer: { status: 'sec_reference_unavailable', cik: null, name: null, exchange: null },
  sec_industry: { status: 'industry_reference_unavailable', code: null, description: null },
})

const sample = {
  version: 'research-decision-desk-v1',
  source_kind: 'frozen_checkpoint', signal_session: '2026-11-13',
  recorded_at_utc: '2026-11-14T22:00:00+00:00',
  source_recent: true, source_age_hours: 20,
  considered_count: 2, displayed_count: 2, quality_passed_count: 1,
  prediction_status: 'insufficient_evidence',
  candidates: [item('AAA', true), item('BBB', false)],
  caveats: ['Scanner rank reflects historical heuristics, not expected returns.'],
}

describe('Research Decision Desk', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => sample })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

  it('shows source provenance, quality reasons, and withheld prediction evidence', async () => {
    render(<MemoryRouter><DecisionDeskPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('AAA Corporation Common Stock')).toBeTruthy())
    expect(screen.getByText(/Last stock-price date: 2026-11-13/)).toBeTruthy()
    expect(screen.getByText(/Historical price below \$5/)).toBeTruthy()
    expect(screen.getByText(/Not enough real results yet/)).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith('/api/research/decision-desk')
  })

  it('filters rejected candidates without calling the backend again', async () => {
    render(<MemoryRouter><DecisionDeskPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('AAA Corporation Common Stock')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('Quality filter'), { target: { value: 'excluded' } })
    expect(screen.queryByText('AAA Corporation Common Stock')).toBeNull()
    expect(screen.getByText('BBB Corporation Common Stock')).toBeTruthy()
    fireEvent.change(screen.getByLabelText('Search research candidates'), { target: { value: 'AAA' } })
    expect(screen.getByText('No candidates match this filter.')).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('does not publish candidate details after an evidence error', async () => {
    fetchMock.mockRejectedValue(new Error('/private/journal/path'))
    render(<MemoryRouter><DecisionDeskPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.queryByText('AAA Corporation Common Stock')).toBeNull()
    expect(screen.queryByText(/private\/journal/)).toBeNull()
  })

  it('offers an empty state without inventing ranked candidates', async () => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => ({
      ...sample, candidates: [], source_kind: null, displayed_count: 0,
      considered_count: 0, quality_passed_count: 0,
    }) })
    render(<MemoryRouter><DecisionDeskPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/No completed website scan or verified saved checkpoint/)).toBeTruthy())
    expect(screen.getByText(/No recorded candidates to inspect/)).toBeTruthy()
  })
})
