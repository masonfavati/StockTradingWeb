import { StrictMode } from 'react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import InvestingHomePage from './InvestingHomePage'

const example = {
  version: '3k-visual-growth-research-v1',
  plan: { budget_usd: '100.00', invested_usd: '55.00', cash_usd: '45.00',
    horizon: 'long', forecast_period: '6m', forecast_horizon_sessions: 120,
    current_model_status: 'historical_backtest_only_not_prospectively_validated',
    exploratory: false, declined: [], warning: 'Not a real investment recommendation.',
    allocation: [
      {symbol: 'SPY', category: 'diversified_core', amount_usd: '55.00', percent_of_budget: 55, why: 'Diversified core'},
      {symbol: null, category: 'cash', amount_usd: '45.00', percent_of_budget: 45, why: 'Unspent budget'},
    ],
  },
  selection: {source: 'user_selected_tickers_not_entire_market', session: ''},
  ranked_stocks: [{symbol: 'AAPL', estimated_change_pct: 6.5,
    historical_analogue_low_pct: -17, historical_analogue_high_pct: 15,
    current_adjusted_price: 100, estimated_end_price_usd: 106.5,
    analogue_low_price_usd: 83, analogue_high_price_usd: 115,
    as_of: '2026-11-13', status: 'unvalidated', history_sessions: 1000,
    backtest: {disjoint_test_windows: 5, beats_average_baseline: false,
      model_average_error_pp: 12, baseline_average_error_pp: 11,
      direction_correct_pct: 40}}],
  benchmark: {symbol: 'SPY', horizon: '6m', estimated_change_pct: 3},
  preview_history: {AAPL: [
    {date: '2026-11-10', adjusted_close: 95},
    {date: '2026-11-11', adjusted_close: 98},
    {date: '2026-11-13', adjusted_close: 100},
  ]},
  history_source: 'Alpaca daily bars',
  evidence_grade: 'experimental_not_prospectively_validated',
  important: 'Past performance is not a guarantee.',
}

const fetchMock = vi.fn()
beforeEach(() => {
  fetchMock.mockReset()
  vi.stubGlobal('fetch', fetchMock)
})
afterEach(() => vi.unstubAllGlobals())
const renderPage = () => render(<MemoryRouter><InvestingHomePage /></MemoryRouter>)

describe('Visual investment home', () => {
  it('does not scan or request a forecast until the user asks', () => {
    renderPage()
    expect(screen.getByRole('heading', {name: /How could I spread out my investment/i})).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects an impossible budget before any provider request', () => {
    renderPage()
    fireEvent.change(screen.getByLabelText('Investment budget'), {target: {value: '0'}})
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    expect(screen.getByRole('alert').textContent).toContain('Enter a valid budget')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('does not invent a price chart when preview history is unavailable', async () => {
    fetchMock.mockResolvedValue({ok: true, json: async () => ({...example, preview_history: {}})})
    renderPage()
    fireEvent.change(screen.getByLabelText('Optional stock symbols'), {target: {value: 'AAPL'}})
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    await waitFor(() => expect(screen.getByText('Your illustrated money split')).toBeTruthy())
    expect(screen.queryByRole('img', {name: /experimental future endpoint range/i})).toBeNull()
  })

  it('renders an accessible budget graphic and experimental chart labels', async () => {
    fetchMock.mockResolvedValue({ok: true, json: async () => example})
    renderPage()
    fireEvent.change(screen.getByLabelText('Optional stock symbols'), {target: {value: 'AAPL'}})
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    await waitFor(() => expect(screen.getByText('Your illustrated money split')).toBeTruthy())
    expect(screen.getByRole('img', {name: /Pie chart showing the budget split/})).toBeTruthy()
    expect(screen.getByRole('img', {name: /experimental future endpoint range/})).toBeTruthy()
    expect(screen.getByText(/Only stocks you entered are compared/)).toBeTruthy()
    expect(fetchMock.mock.calls[0][0]).toBe('/api/investing/plan')
    const request = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    expect(request.allow_exploratory).toBe(false)
  })

  it('shows a core-and-cash illustration when a finished scan has no verified stock shortlist', async () => {
    const noStocks = {
      ...example,
      plan: {...example.plan, exploratory: false},
      selection: {source: 'completed_scan_no_verified_shortlist', session: '2026-11-13',
        note: 'The market search finished, but no current individual-stock shortlist passed all required checks.'},
      ranked_stocks: [],
      preview_history: {},
    }
    fetchMock
      .mockResolvedValueOnce({ok: false, status: 409, json: async () => ({detail: 'No fresh full-market shortlist'})})
      .mockResolvedValueOnce({ok: true, status: 202, json: async () => ({state: 'running'})})
      .mockResolvedValueOnce({ok: true, status: 200, json: async () => ({
        state: 'complete', message: 'Scan complete.', processed: 100, considered: 100,
      })})
      .mockResolvedValueOnce({ok: true, status: 200, json: async () => noStocks})

    render(<StrictMode><MemoryRouter><InvestingHomePage /></MemoryRouter></StrictMode>)
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))

    await waitFor(() => expect(screen.getByText('Your illustrated money split')).toBeTruthy())
    expect(screen.getByText('Individual-stock research status')).toBeTruthy()
    expect(screen.getByRole('status').textContent).toContain('no current individual-stock shortlist passed')
    expect(screen.getByText('No individual-stock forecasts are available from this market scan.')).toBeTruthy()
    expect(screen.queryByRole('alert')).toBeNull()
    expect((screen.getByRole('button', {name: 'Build my investment picture'}) as HTMLButtonElement).disabled).toBe(false)
    expect(fetchMock.mock.calls.map((call: unknown[]) => call[0])).toEqual([
      '/api/investing/plan', '/api/scanner/scan', '/api/scanner/status', '/api/investing/plan',
    ])
  })

  it('polls a launched market scan and clears the spinner under React StrictMode', async () => {
    // StrictMode's development-only effect cleanup used to set stopped=true
    // forever, so no GET /status happened and the button stayed disabled.
    fetchMock
      .mockResolvedValueOnce({ok: false, status: 409, json: async () => ({detail: 'No fresh full-market shortlist'})})
      .mockResolvedValueOnce({ok: true, status: 202, json: async () => ({state: 'running'})})
      .mockResolvedValueOnce({ok: true, status: 200, json: async () => ({
        state: 'complete', message: 'Scan complete.', processed: 100, considered: 100,
      })})
      .mockResolvedValueOnce({ok: true, status: 200, json: async () => ({
        ...example,
        selection: {source: 'latest_full_market_scan', session: '2026-11-13'},
      })})

    render(<StrictMode><MemoryRouter><InvestingHomePage /></MemoryRouter></StrictMode>)
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))

    await waitFor(() => expect(screen.getByText('Your illustrated money split')).toBeTruthy())
    expect(fetchMock.mock.calls.map((call: unknown[]) => call[0])).toEqual([
      '/api/investing/plan',
      '/api/scanner/scan',
      '/api/scanner/status',
      '/api/investing/plan',
    ])
    expect((screen.getByRole('button', {name: 'Build my investment picture'}) as HTMLButtonElement).disabled).toBe(false)
    expect(screen.queryByText('Studying the market…')).toBeNull()
    expect(screen.queryByRole('alert')).toBeNull()
  })

  it('reports scanner failure instead of spinning forever in StrictMode', async () => {
    fetchMock
      .mockResolvedValueOnce({ok: false, status: 409, json: async () => ({detail: 'No fresh full-market shortlist'})})
      .mockResolvedValueOnce({ok: true, status: 202, json: async () => ({state: 'running'})})
      .mockResolvedValueOnce({ok: true, status: 200, json: async () => ({
        state: 'failed', message: 'Scan failed.', processed: 0, considered: 0,
      })})

    render(<StrictMode><MemoryRouter><InvestingHomePage /></MemoryRouter></StrictMode>)
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    await waitFor(() => expect(screen.getByRole('alert').textContent).toContain('market search failed'))
    expect((screen.getByRole('button', {name: 'Build my investment picture'}) as HTMLButtonElement).disabled).toBe(false)
    expect(fetchMock.mock.calls.map((call: unknown[]) => call[0])).toEqual([
      '/api/investing/plan', '/api/scanner/scan', '/api/scanner/status',
    ])
  })

  it('shows negative MKTX research without presenting it as an investment allocation', async () => {
    const negative = {
      ...example,
      selection: {source: 'latest_full_market_scan', session: '2026-11-13'},
      ranking_scope: {complete_market_forecast: false, market_symbols_screened: 8000,
        preliminary_candidates_quality_screened: 700, symbols_selected_for_forecast: 11,
        symbols_with_estimates: 10},
      plan: {...example.plan, exploratory: true, declined: [
        {symbol: 'MKTX', reason: 'Estimated change -11.70% is not positive'},
      ]},
      ranked_stocks: [{...example.ranked_stocks[0], symbol: 'MKTX',
        estimated_change_pct: -11.7, estimated_end_price_usd: 88.3}],
      preview_history: {},
    }
    fetchMock.mockResolvedValue({ok: true, json: async () => negative})
    renderPage()
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    await waitFor(() => expect(screen.getByText('Your illustrated money split')).toBeTruthy())
    expect(screen.getByText(/Excluded from money split: estimated change is not positive/)).toBeTruthy()
    expect(screen.getByText(/8,000 symbols received the preliminary market scan/)).toBeTruthy()
    expect(screen.getByText(/The model has not forecast every stock/)).toBeTruthy()
    expect(screen.getByText(/not the entire 5\+ year holding period/)).toBeTruthy()
    expect(screen.getByText(/No individual stock passed the complete allocation decision/)).toBeTruthy()
  })


  it('shows separate dollar contributions for risk-screened individual stocks', async () => {
    const withStocks = {
      ...example,
      selection: {source: 'latest_full_market_scan', session: '2026-11-13'},
      plan: {
        ...example.plan, exploratory: true, invested_usd: '75.00', cash_usd: '25.00',
        combination_analysis: {
          method: 'bounded_risk_adjusted_historical_heuristic_not_probability',
          forecasted_stocks_reviewed: 2, positive_estimate_stocks: 2,
          risk_eligible_stocks: 2, combinations_considered: 3,
          stock_positions_selected: 2, illustrative_model_gain_usd: '5.00',
        },
        allocation: [
          {symbol: 'SPY', category: 'diversified_core', amount_usd: '55.00', percent_of_budget: 55, why: 'Diversified core'},
          {symbol: 'AAA', category: 'experimental_stock', amount_usd: '10.00', percent_of_budget: 10, why: 'Risk-adjusted idea'},
          {symbol: 'BBB', category: 'experimental_stock', amount_usd: '10.00', percent_of_budget: 10, why: 'Different risk-adjusted idea'},
          {symbol: null, category: 'cash', amount_usd: '25.00', percent_of_budget: 25, why: 'Cash'},
        ],
      },
      ranked_stocks: [
        {...example.ranked_stocks[0], symbol: 'AAA', estimated_change_pct: 35},
        {...example.ranked_stocks[0], symbol: 'BBB', estimated_change_pct: 18},
      ],
      preview_history: {},
    }
    fetchMock.mockResolvedValue({ok: true, json: async () => withStocks})
    renderPage()
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    await waitFor(() => expect(screen.getByText('Illustrative contributions to individual stocks')).toBeTruthy())
    expect(screen.getByText(/2 of 2 forecasted stocks passed/)).toBeTruthy()
    expect(screen.getByText(/3 combinations were evaluated/)).toBeTruthy()
    expect(screen.getAllByText('$10.00').length).toBeGreaterThanOrEqual(2)
    expect(screen.getByRole('img', {name: /Pie chart showing the budget split between individual stocks/})).toBeTruthy()
  })


  it('compares the fund, mixed and optimized return approaches using one market request', async () => {
    const comparison = {
      forecast_period: '6m', forecast_horizon_sessions: 120,
      method_warning: 'Unvalidated short-horizon estimate; past results do not limit future losses.',
      approaches: [
        {
          id: 'combined', label: 'SPY + eligible individual stocks', available: true,
          invested_usd: '75.00', cash_usd: '25.00', stock_positions: 2,
          illustrative_model_gain_usd: '5.20',
          past_window_range: {windows_compared: 5, worst_observed_change_pct: -12.4,
            best_observed_change_pct: 10.1},
          allocation: [
            {symbol: 'SPY', category: 'diversified_core', amount_usd: '55.00', percent_of_budget: 55, why: 'Fund'},
            {symbol: 'AAA', category: 'experimental_stock', amount_usd: '10.00', percent_of_budget: 10, why: 'Stock'},
            {symbol: 'BBB', category: 'experimental_stock', amount_usd: '10.00', percent_of_budget: 10, why: 'Stock'},
            {symbol: null, category: 'cash', amount_usd: '25.00', percent_of_budget: 25, why: 'Cash'},
          ],
          explanation: 'Combined portfolio illustration.',
        },
        {
          id: 'core_only', label: 'SPY fund + cash', available: true,
          invested_usd: '55.00', cash_usd: '45.00', stock_positions: 0,
          illustrative_model_gain_usd: '2.00',
          past_window_range: {windows_compared: 5, worst_observed_change_pct: -8.1,
            best_observed_change_pct: 7.0},
          allocation: [
            {symbol: 'SPY', category: 'diversified_core', amount_usd: '55.00', percent_of_budget: 55, why: 'Fund'},
            {symbol: null, category: 'cash', amount_usd: '45.00', percent_of_budget: 45, why: 'Cash'},
          ],
          explanation: 'Diversified fund only.',
        },
        {
          id: 'max_model_change', label: 'Highest experimental model dollar change', available: true,
          winning_structure: 'stocks_and_cash', combinations_considered: 13,
          invested_usd: '20.00', cash_usd: '80.00', stock_positions: 2,
          illustrative_model_gain_usd: '3.20',
          past_window_range: {windows_compared: 5, worst_observed_change_pct: -14.3,
            best_observed_change_pct: 12.0},
          allocation: [
            {symbol: 'AAA', category: 'experimental_stock', amount_usd: '10.00', percent_of_budget: 10, why: 'Stock'},
            {symbol: 'BBB', category: 'experimental_stock', amount_usd: '10.00', percent_of_budget: 10, why: 'Stock'},
            {symbol: null, category: 'cash', amount_usd: '80.00', percent_of_budget: 80, why: 'Cash'},
          ],
          explanation: 'Selected: Eligible stocks + cash after 13 eligible combinations.',
        },
      ],
    }
    fetchMock.mockResolvedValue({ok: true, json: async () => ({
      ...example, scenario_comparison: comparison,
    })})
    renderPage()
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    await waitFor(() => expect(screen.getByRole('heading', {name: 'Compare three ways to use this budget'})).toBeTruthy())
    expect(screen.getByText('SPY fund + cash')).toBeTruthy()
    expect(screen.getByText('Highest experimental model dollar change')).toBeTruthy()
    expect(screen.getByText(/Selected: Eligible stocks \+ cash after 13/)).toBeTruthy()
    expect(screen.getAllByText(/Worst observed same-length historical window/)).toHaveLength(3)
    expect(screen.getByText(/Unvalidated short-horizon estimate/)).toBeTruthy()
    expect(fetchMock).toHaveBeenCalledTimes(1)
  })

  it('marks the maximum-change portfolio unavailable when securities are not verified', async () => {
    const unavailable = {
      ...example,
      scenario_comparison: {
        forecast_period: '6m', forecast_horizon_sessions: 120,
        method_warning: 'No trading recommendations are made.',
        approaches: [{
          id: 'max_model_change', label: 'Highest experimental model dollar change', available: false,
          invested_usd: '0.00', cash_usd: '100.00', stock_positions: 0,
          illustrative_model_gain_usd: null, past_window_range: null,
          allocation: [{symbol: null, category: 'cash', amount_usd: '100.00', percent_of_budget: 100, why: 'Cash'}],
          explanation: 'Quality-verified full-market shortlist required.',
        }],
      },
    }
    fetchMock.mockResolvedValue({ok: true, json: async () => unavailable})
    renderPage()
    fireEvent.click(screen.getByRole('button', {name: 'Build my investment picture'}))
    await waitFor(() => expect(screen.getByText('Maximum-change comparison unavailable')).toBeTruthy())
    expect(screen.getByText('Quality-verified full-market shortlist required.')).toBeTruthy()
    expect(screen.queryByText(/Experimental 6m model dollar change/)).toBeNull()
  })

})
