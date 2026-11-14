export interface WatchedCompany {
  id: number
  symbol: string
  name: string
  tradable: boolean | null
  added_at: string
}

export interface CompanySuggestion {
  symbol: string
  name: string
  tradable: boolean
}

async function readJson<T>(url: string, options?: RequestInit): Promise<T> {
  const response = await fetch(url, options)
  if (!response.ok) {
    let detail = `Request failed (${response.status}).`
    try {
      const payload: unknown = await response.json()
      if (
        typeof payload === 'object' && payload !== null &&
        'detail' in payload && typeof payload.detail === 'string'
      ) {
        detail = payload.detail
      }
    } catch {
      // Keep the generic error if the server did not return JSON.
    }
    throw new Error(detail)
  }
  return (await response.json()) as T
}

export function fetchWatchlist(): Promise<WatchedCompany[]> {
  return readJson<WatchedCompany[]>('/api/watchlist')
}

export function searchCompanies(query: string): Promise<CompanySuggestion[]> {
  return readJson<CompanySuggestion[]>(
    `/api/watchlist/search?q=${encodeURIComponent(query)}`,
  )
}

export function saveCompany(symbol: string): Promise<WatchedCompany> {
  return readJson<WatchedCompany>('/api/watchlist', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ symbol }),
  })
}

export async function removeCompany(symbol: string): Promise<void> {
  const response = await fetch(`/api/watchlist/${encodeURIComponent(symbol)}`, {
    method: 'DELETE',
  })
  if (!response.ok) {
    throw new Error(`Couldn't remove this company (${response.status}).`)
  }
}
