import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import WatchlistPage from './WatchlistPage'

class FakeEventSource {
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: ((event: Event) => void) | null = null
  readonly url: string

  constructor(url: string) {
    this.url = url
  }

  close() {}
}

let saved: { id: number; symbol: string; name: string; tradable: boolean; added_at: string }[]

function respond(payload: unknown, status = 200): Response {
  return {
    ok: status >= 200 && status < 300,
    status,
    json: async () => payload,
  } as Response
}

function renderPage() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false, refetchOnWindowFocus: false } },
  })
  return render(<QueryClientProvider client={client}><WatchlistPage /></QueryClientProvider>)
}

describe('Beginner-friendly watchlist', () => {
  beforeEach(() => {
    saved = []
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('fetch', vi.fn(async (input: string | URL | Request, options?: RequestInit) => {
      const url = String(input)
      if (url === '/api/watchlist' && options?.method === 'POST') {
        const company = {
          id: 1, symbol: 'AAPL', name: 'Apple Inc.', tradable: true,
          added_at: '2026-11-14T15:00:00Z',
        }
        saved.push(company)
        return respond(company, 201)
      }
      if (url === '/api/watchlist') return respond(saved)
      if (url.startsWith('/api/watchlist/search?')) {
        return respond([{ symbol: 'AAPL', name: 'Apple Inc.', tradable: true }])
      }
      return respond({}, 404)
    }))
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('explains that following a company does not buy shares', async () => {
    renderPage()
    expect(screen.getByText(/Following a stock does not buy it/)).toBeInTheDocument()
    await waitFor(() => expect(screen.getByText(/Nothing saved yet/)).toBeInTheDocument())
  })

  it('can find Apple by company name and save it', async () => {
    renderPage()
    fireEvent.change(screen.getByLabelText('Company name or stock symbol'), {
      target: { value: 'Apple' },
    })
    fireEvent.click(screen.getByRole('button', { name: 'Find companies' }))
    await waitFor(() => expect(screen.getByRole('button', { name: 'Follow' })).toBeInTheDocument())
    fireEvent.click(screen.getByRole('button', { name: 'Follow' }))
    await waitFor(() => expect(screen.getByRole('heading', { name: 'Apple Inc.' })).toBeInTheDocument())
    expect(screen.getByText(/This did not buy any shares/)).toBeInTheDocument()
  })
})
