import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import PredictionLabPage from './PredictionLabPage'

const pending = {
  version: 'prospective-conditional-logit-v1',
  target: 'Selected stock beats SPY after 20 sessions',
  research_rule: 'completed-sip-all-descriptive-momentum-volatility-v1',
  holding_sessions: 20, status: 'insufficient_evidence',
  source_sha256: 'a'.repeat(64), completed_compatible_windows: 0,
  completed_candidate_outcomes: 0, journal_status_counts: { PENDING: 1 },
  walk_forward: {
    validation_windows: 0, validation_candidates: 0, nonoverlapping_validation_windows: 0,
    brier_score: null, expanding_prior_brier_score: null, brier_improvement: null,
    top_two_mean_excess_vs_spy_pp: null, top_two_mean_vs_original_scan_pp: null,
    top_two_windows_beating_spy: 0,
    checks: { at_least_20_walk_forward_windows: false }, research_gate_passed: false,
  },
  method: 'Fixed-feature walk-forward logistic evaluation',
  warnings: ['Only independent forward records can contribute.'],
}

describe('PredictionLabPage', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => pending })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals() })

  it('shows real no-data status without fabricating model accuracy', async () => {
    render(<MemoryRouter><PredictionLabPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByTestId('prediction-status').textContent).toMatch(/insufficient evidence/))
    expect(fetchMock).toHaveBeenCalledWith('/api/research/prediction-validation')
    expect(screen.getAllByText('Not available').length).toBeGreaterThan(0)
    expect(screen.getByText(/Additional genuinely matured outcomes are needed/)).toBeTruthy()
  })

  it('shows walk-forward scores and their comparison without claiming guaranteed gains', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      ...pending, status: 'not_validated', completed_compatible_windows: 40,
      walk_forward: {
        ...pending.walk_forward, validation_windows: 5, validation_candidates: 100,
        brier_score: 0.245, expanding_prior_brier_score: 0.25,
      },
    }) })
    render(<MemoryRouter><PredictionLabPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('0.245')).toBeTruthy())
    expect(screen.getByText(/Overlapping test periods are correlated/)).toBeTruthy()
    expect(screen.getByText(/does not predict a future stock price/)).toBeTruthy()
  })

  it('fails closed when the local evidence audit is unavailable', async () => {
    fetchMock.mockRejectedValueOnce(new Error('Private journal path is corrupt'))
    render(<MemoryRouter><PredictionLabPage /></MemoryRouter>)
    await waitFor(() => expect(screen.getByRole('alert')).toBeTruthy())
    expect(screen.queryByTestId('prediction-status')).toBeNull()
    expect(screen.queryByText(/Private journal path is corrupt/)).toBeNull()
  })
})
