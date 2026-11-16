import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import ScannerPage from './ScannerPage'

const idle = {
  state: 'idle', message: 'No scan has been run yet.', started_at: null,
  completed_at: null, latest_session: null,
  directory_size: 0, considered: 0, processed: 0, qualified: 0, candidates: [],
}

const running = { ...idle, state: 'running', message: 'Loading market directory...' }

describe('ScannerPage', () => {
  const fetchMock = vi.fn()

  beforeEach(() => {
    fetchMock.mockImplementation(async (url: string, options?: RequestInit) => ({
      ok: true,
      json: async () => (url === '/api/scanner/scan' && options?.method === 'POST' ? running : idle),
    }))
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

  it('explains why a low price is not a buy signal', async () => {
    render(<ScannerPage />)
    expect(screen.getByText(/A low share price by itself does not make a stock more likely to rise/i)).toBeTruthy()
    await waitFor(() => expect(screen.getByText(/No scan has been run yet/i)).toBeTruthy())
  })

  it('triggers broad-market screening only when clicked', async () => {
    render(<ScannerPage />)
    await waitFor(() => expect(fetchMock).toHaveBeenCalledWith('/api/scanner/status', undefined))
    fireEvent.click(screen.getByRole('button', { name: 'Find Opportunities' }))
    await waitFor(() => {
      expect(fetchMock).toHaveBeenCalledWith('/api/scanner/scan', { method: 'POST' })
    })
  })
})
