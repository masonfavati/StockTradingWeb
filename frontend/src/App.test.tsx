import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import App from './App'

const emptyPortfolio = {
  summary: {
    holdings: [], recorded_trades: 0, realized_gain_usd: '0.00',
    estimated_portfolio_value_usd: '0.00', valuation_complete: true,
    caveat: 'These are manual records, not confirmed brokerage trades.',
  },
  trades: [],
}

beforeEach(() => {
  vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
    ok: true, json: async () => emptyPortfolio,
  }))
})
afterEach(() => vi.unstubAllGlobals())

function renderApp() {
  render(<MemoryRouter initialEntries={['/']}><App /></MemoryRouter>)
}

describe('Application shell', () => {
  it('shows the beginner-friendly investment plan on the home route', () => {
    renderApp()
    expect(screen.getByRole('heading', {name: 'How could I spread out my investment?'})).toBeInTheDocument()
    expect(screen.getByRole('link', {name: 'Build My Investment Plan'})).toHaveAttribute('aria-current', 'page')
  })

  it('navigates to the manual holdings page', () => {
    renderApp()
    fireEvent.click(screen.getByRole('link', {name: 'My Holdings'}))
    expect(screen.getByRole('heading', {name: 'Track what you actually bought'})).toBeInTheDocument()
    expect(screen.getByRole('heading', {name: 'Record a purchase or sale'})).toBeInTheDocument()
  })

  it('honestly states the holdings tracker does not place real trades', () => {
    renderApp()
    fireEvent.click(screen.getByRole('link', {name: 'My Holdings'}))
    expect(screen.getByText(/private local record, not connected to a brokerage account/i)).toBeInTheDocument()
    expect(screen.getByText(/Nothing is traded/i)).toBeInTheDocument()
  })
})
