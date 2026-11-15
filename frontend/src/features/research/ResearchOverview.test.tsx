import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import ResearchOverview from './ResearchOverview'

const journal = {
  generated_at_utc: '2026-11-15T00:00:00Z', registered_checkpoints: 1,
  status_counts: { PENDING: 1, READY: 0, COMPLETE: 0, INCOMPLETE: 0, NO_SELECTION: 0 },
  groups: [], warnings: [], latest_checkpoint: null,
}

const emptyScan = {
  state: 'idle', message: 'No scan', started_at: null, completed_at: null,
  latest_session: null, directory_size: 0, considered: 0, processed: 0,
  qualified: 0, candidates: [],
}

describe('ResearchOverview', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    fetchMock.mockImplementation(async (url: string) => ({
      ok: true, json: async () => url.includes('/research/') ? journal : emptyScan,
    }))
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.clearAllMocks(); vi.unstubAllGlobals() })

  it('shows pending predictions without inventing performance statistics', async () => {
    render(<MemoryRouter><ResearchOverview /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText('Waiting for future outcomes')).toBeTruthy())
    expect(screen.getByText(/No completed, verified outcomes yet/)).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledWith('/api/research/overview')
  })

  it('shows journal unavailable rather than zero return when backend fails', async () => {
    fetchMock.mockImplementation(async (url: string) => ({
      ok: !url.includes('/research/'), json: async () => emptyScan,
    }))
    render(<MemoryRouter><ResearchOverview /></MemoryRouter>)
    await waitFor(() => expect(screen.getByText(/Journal unavailable/)).toBeTruthy())
  })
})
