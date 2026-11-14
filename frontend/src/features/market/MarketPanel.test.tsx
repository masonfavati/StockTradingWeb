import { act, render, screen } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import MarketPanel from './MarketPanel'

class MockEventSource {
  static active: MockEventSource
  static CLOSED = 2

  readyState = 1
  onopen: ((event: Event) => void) | null = null
  onmessage: ((event: MessageEvent<string>) => void) | null = null
  onerror: ((event: Event) => void) | null = null

  readonly url: string

  constructor(url: string) {
    this.url = url
    MockEventSource.active = this
  }

  close() {
    this.readyState = MockEventSource.CLOSED
  }

  emit(data: unknown) {
    this.onmessage?.(
      new MessageEvent('message', {
        data: JSON.stringify(data),
      }),
    )
  }
}

const observation = {
  provider: 'alpaca',
  feed: 'test',
  symbol: 'FAKEPACA',
  coverage: 'synthetic_test',
  connection_status: 'connected',
  data_status: 'simulated',
  trade_fresh: true,
  quote_fresh: false,
  trade_age_seconds: 1,
  quote_age_seconds: null,
  received_at: '2026-11-13T15:00:00Z',
  error: null,
  latest_trade: {
    price: '123.4567',
    size: 10,
    timestamp: '2026-11-13T15:00:00Z',
  },
  latest_quote: null,
}

describe('Live market panel', () => {
  beforeEach(() => {
    vi.stubGlobal('EventSource', MockEventSource)
  })

  afterEach(() => {
    vi.unstubAllGlobals()
  })

  it('displays incoming simulated events accurately', () => {
    render(<MarketPanel />)

    expect(MockEventSource.active.url).toBe('/api/market/events')

    act(() => {
      MockEventSource.active.onopen?.(new Event('open'))
      MockEventSource.active.emit(observation)
    })

    expect(screen.getByRole('status'))
      .toHaveTextContent('SIMULATED DATA')
    expect(screen.getByText('$123.4567')).toBeInTheDocument()
    expect(screen.queryByText('LIVE IEX')).not.toBeInTheDocument()
  })

  it('stops claiming a live connection after failure', () => {
    render(<MarketPanel />)

    act(() => {
      MockEventSource.active.onopen?.(new Event('open'))
      MockEventSource.active.emit({
        ...observation,
        feed: 'iex',
        symbol: 'AAPL',
        coverage: 'iex_only',
        data_status: 'live',
      })
    })

    expect(screen.getByRole('status'))
      .toHaveTextContent('LIVE IEX')

    act(() => {
      MockEventSource.active.readyState = 0
      MockEventSource.active.onerror?.(new Event('error'))
    })

    expect(screen.getByRole('status'))
      .toHaveTextContent('STREAM DISCONNECTED')
  })
})
