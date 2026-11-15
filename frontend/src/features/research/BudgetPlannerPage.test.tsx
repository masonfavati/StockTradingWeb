import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { fireEvent, render, screen, waitFor } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import BudgetPlannerPage from './BudgetPlannerPage'

const sample = {
  budget_usd: '100.00', style: 'balanced', experimental_opt_in: false,
  horizon: 'long', max_loss_usd: null, modeled_risky_principal_usd: '65.00',
  loss_cap_binding: false,
  planning_explanations: ['Five-plus years is an illustration.'],
  stress_scenarios: [
    { decline_percent: 10, loss_usd: '6.50', remaining_budget_usd: '93.50' },
    { decline_percent: 30, loss_usd: '19.50', remaining_budget_usd: '80.50' },
    { decline_percent: 100, loss_usd: '65.00', remaining_budget_usd: '35.00' },
  ],
  scan_usable_for_ideas: false, source_session: null, source_kind: null,
  allocation: [
    { category: 'diversified_core_example', symbol: 'SPY', name: 'Broad U.S. market ETF example (SPY)',
      amount_usd: '65.00', percent_of_budget: 65, indicative_fractional_shares: null,
      historical_price_usd: null, reason: 'Example diversified fund.' },
    { category: 'cash', symbol: null, name: 'Cash / unallocated budget', amount_usd: '35.00',
      percent_of_budget: 35, indicative_fractional_shares: null, historical_price_usd: null, reason: 'Cash.' },
  ],
  total_invested_example_usd: '65.00', unallocated_cash_usd: '35.00',
  illustrative_equity_drop_30pct_usd: '19.50', warnings: ['No orders are created.'],
}

describe('BudgetPlannerPage', () => {
  const fetchMock = vi.fn()
  beforeEach(() => {
    fetchMock.mockResolvedValue({ ok: true, json: async () => sample })
    vi.stubGlobal('fetch', fetchMock)
  })
  afterEach(() => { vi.unstubAllGlobals(); vi.clearAllMocks() })

  it('does not fetch or plan until the person asks', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    expect(fetchMock).not.toHaveBeenCalled()
    expect(screen.getByText(/Educational scenarios only/)).toBeTruthy()
  })

  it('posts the budget and selected style with experimental picks off by default', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      budget_usd: '100.00', style: 'balanced', allow_experimental_stocks: false,
      horizon: 'long', max_loss_usd: null,
    })
    await waitFor(() => expect(screen.getByText('Cash / unallocated budget')).toBeTruthy())
    expect(screen.getByText(/No fresh individual-stock shortlist/)).toBeTruthy()
  })

  it('does not request impossible or fractional-cent budgets', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Investment amount in dollars'), { target: { value: '100.001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('submits the selected horizon and affordable-loss ceiling', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('When might you need this money?'), { target: { value: 'medium' } })
    fireEvent.change(screen.getByLabelText('Maximum affordable loss in dollars'), { target: { value: '25.00' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string)).toEqual({
      budget_usd: '100.00', style: 'balanced', allow_experimental_stocks: false,
      horizon: 'medium', max_loss_usd: '25.00',
    })
  })

  it('rejects an affordable-loss number above the budget without calling the API', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Maximum affordable loss in dollars'), { target: { value: '100.01' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('rejects fractional-cent affordable loss without calling the API', () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.change(screen.getByLabelText('Maximum affordable loss in dollars'), { target: { value: '25.001' } })
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    expect(screen.getByRole('alert')).toBeTruthy()
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('clears a previous plan whenever the planning inputs change', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Why these amounts?')).toBeTruthy())
    fireEvent.change(screen.getByLabelText('When might you need this money?'), { target: { value: 'short' } })
    expect(screen.queryByText('Why these amounts?')).toBeNull()
  })

  it('explains losses under the stress scenarios', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Hypothetical downside scenarios')).toBeTruthy())
    expect(screen.getByText('Risky assets fall 100%')).toBeTruthy()
    expect(screen.getByText('No personal affordable-loss cap was provided.', { exact: false })).toBeTruthy()
  })

  it('experimental picks require an explicit opt-in', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string).allow_experimental_stocks).toBe(true)
  })

  it('shows explicit historical quality rules and exclusions when experimental analysis runs', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      ...sample,
      experimental_opt_in: true,
      quality_review: {
        version: 'descriptive-quality-screen-v1', applied: true,
        screened_count: 3, selected_count: 1,
        excluded_counts: { below_liquidity_screen: 2 },
        thresholds: {
          min_adjusted_close_usd: 5,
          min_approx_daily_dollar_volume_usd: 5_000_000,
          max_annualized_volatility_pct: 80,
          min_60d_drawdown_pct: -25,
          max_individual_stocks: 2,
        },
        caveat: 'No correlation model or verified company identity.',
      },
    }) })
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Individual-stock research quality checks')).toBeTruthy())
    expect(screen.getByText(/Reviewed 3 ranked shortlist candidates/)).toBeTruthy()
    expect(screen.getByText(/Below approximate historical trading-volume threshold: 2/)).toBeTruthy()
    expect(screen.getByText('No correlation model or verified company identity.')).toBeTruthy()
  })

  it('explains why experimental screening was not applied instead of inventing candidates', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      ...sample, experimental_opt_in: true,
      quality_review: { applied: false },
    }) })
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText(/No quality screening was applied/)).toBeTruthy())
  })
  it('asks for strict historical co-movement evidence only when experimental stocks are enabled', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    let [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string).require_historical_comovement).toBeUndefined()
    fireEvent.click(screen.getByRole('checkbox'))
    expect(screen.getByLabelText('Require historical co-movement evidence')).toBeTruthy()
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const [, secondInit] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(JSON.parse(secondInit.body as string).require_historical_comovement).toBe(true)
  })

  it('turning off the evidence requirement clears the old allocation', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Why these amounts?')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('Require historical co-movement evidence'))
    expect(screen.queryByText('Why these amounts?')).toBeNull()
  })

  it('explains rejected stock pairs and retrospective portfolio risk', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      ...sample,
      experimental_opt_in: true,
      historical_comovement_required: true,
      comovement_review: {
        version: 'adjusted-return-comovement-v1', status: 'checked',
        requested_symbols: ['AAA', 'BBB'], approved_symbols: ['AAA'],
        excluded: [{ symbol: 'BBB', reason: 'high_positive_correlation' }],
        matched_sessions: 61, pairwise_correlations: [
          { symbol_a: 'AAA', symbol_b: 'BBB', correlation: 0.94, paired_returns: 60 },
        ],
        spy_correlations: [{ symbol: 'AAA', correlation: 0.75, paired_returns: 60 }],
        portfolio_annualized_historical_volatility_pct: 15.4,
        portfolio_historical_max_drawdown_pct: -7.2,
        threshold_positive_correlation: 0.8,
        caveat: 'Not a validated portfolio strategy.',
      },
    }) })
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Historical co-movement and portfolio risk')).toBeTruthy())
    expect(screen.getByText(/AAA\/BBB: 0.94/)).toBeTruthy()
    expect(screen.getByText(/BBB: high positive correlation/)).toBeTruthy()
    expect(screen.getByText(/15.40%/)).toBeTruthy()
    expect(screen.getByText('Not a validated portfolio strategy.')).toBeTruthy()
  })


  it('enables SEC evidence only when the experimental opt-in is on', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    expect(screen.queryByLabelText('Require SEC filer cross-reference')).toBeNull()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByLabelText('Require SEC filer cross-reference'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    expect(JSON.parse(init.body as string).require_sec_identity).toBe(true)
  })

  it('clears a former result when SEC identity evidence is toggled', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Why these amounts?')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('Require SEC filer cross-reference'))
    expect(screen.queryByText('Why these amounts?')).toBeNull()
  })

  it('explains verified filer identity and evidence limits', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      ...sample,
      experimental_opt_in: true,
      sec_identity_required: true,
      sec_identity_review: {
        version: 'sec-ticker-crossref-v1', status: 'checked',
        requested_symbols: ['AAA', 'BBB'], approved_symbols: ['AAA'],
        imported_at_utc: '2026-11-15T02:00:00+00:00',
        source_url: 'https://www.sec.gov/files/company_tickers_exchange.json',
        source_sha256: 'abc',
        matches: [{ symbol: 'AAA', cik: '0000001001', sec_filer_name: 'ALPHA INC', sec_exchange: 'Nasdaq' }],
        excluded: [{ symbol: 'BBB', reason: 'sec_ticker_not_found' }],
        caveat: 'Not verified common shares, sector classification, or return forecasts.',
      },
    }) })
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('SEC ticker-to-filer cross-reference')).toBeTruthy())
    expect(screen.getByText(/AAA: SEC filer ALPHA INC/)).toBeTruthy()
    expect(screen.getByText(/BBB: sec ticker not found/)).toBeTruthy()
    expect(screen.getByText('Not verified common shares, sector classification, or return forecasts.')).toBeTruthy()
  })

  it('SIC evidence is opt-in and also requires the SEC filer cross-reference', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    expect(screen.queryByLabelText('Require SEC SIC industry evidence')).toBeNull()
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByLabelText('Require SEC SIC industry evidence'))
    expect((screen.getByLabelText('Require SEC filer cross-reference') as HTMLInputElement).checked).toBe(true)
    expect((screen.getByLabelText('Require SEC filer cross-reference') as HTMLInputElement).disabled).toBe(true)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1))
    const [, init] = fetchMock.mock.calls[0] as [string, RequestInit]
    const posted = JSON.parse(init.body as string)
    expect(posted.require_sec_industry).toBe(true)
    expect(posted.require_sec_identity).toBe(true)
  })

  it('SIC option clears previously calculated allocations', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Why these amounts?')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('Require SEC SIC industry evidence'))
    expect(screen.queryByText('Why these amounts?')).toBeNull()
  })

  it('displays SIC classifications and cash-preserving exclusions', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      ...sample,
      experimental_opt_in: true,
      sec_industry_required: true,
      sec_industry_review: {
        version: 'sec-sic-filer-industry-v1', status: 'checked',
        requested_symbols: ['AAA', 'BBB'], approved_symbols: ['AAA'],
        matches: [
          { symbol: 'AAA', cik: '0000001001', sic: '3571', sic_description: 'Electronic Computers' },
          { symbol: 'BBB', cik: '0000001002', sic: '3571', sic_description: 'Electronic Computers' },
        ],
        excluded: [{ symbol: 'BBB', reason: 'same_reported_sic_as_prior_stock' }],
        imported_at_utc: '2026-11-15T12:00:00+00:00',
        source_sha256: 'abc', source_url: 'https://www.sec.gov/Archives/edgar/daily-index/bulkdata/submissions.zip',
        caveat: 'Not an independent sector-exposure guarantee.',
      },
    }) })
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('SEC-reported SIC industry evidence')).toBeTruthy())
    expect(screen.getByText(/AAA: SEC SIC 3571/)).toBeTruthy()
    expect(screen.getByText(/BBB: same reported sic as prior stock/)).toBeTruthy()
    expect(screen.getByText('Not an independent sector-exposure guarantee.')).toBeTruthy()
  })

  it('prediction-evidence switch is opt-in and clears a previous budget example', async () => {
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    expect(screen.queryByLabelText('Require prospective prediction evidence')).toBeNull()
    fireEvent.click(screen.getByRole('checkbox'))
    expect((screen.getByLabelText('Require prospective prediction evidence') as HTMLInputElement).checked).toBe(false)
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Why these amounts?')).toBeTruthy())
    fireEvent.click(screen.getByLabelText('Require prospective prediction evidence'))
    expect(screen.queryByText('Why these amounts?')).toBeNull()
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2))
    const [, init] = fetchMock.mock.calls[1] as [string, RequestInit]
    expect(JSON.parse(init.body as string).require_prediction).toBe(true)
  })

  it('displays withheld prediction evidence and the cash-preservation warning', async () => {
    fetchMock.mockResolvedValueOnce({ ok: true, json: async () => ({
      ...sample, experimental_opt_in: true, prediction_required: true,
      prediction_review: {
        version: 'prospective-conditional-logit-v1', status: 'insufficient_evidence',
        requested_symbols: ['AAA'], approved_symbols: [], scores: [],
        excluded: [{ symbol: 'AAA', reason: 'no_published_predictive_evidence' }],
        caveat: 'No prospectively validated evidence; cash retained.',
      },
    }) })
    render(<MemoryRouter><BudgetPlannerPage /></MemoryRouter>)
    fireEvent.click(screen.getByRole('checkbox'))
    fireEvent.click(screen.getByLabelText('Require prospective prediction evidence'))
    fireEvent.click(screen.getByRole('button', { name: 'Show budget example' }))
    await waitFor(() => expect(screen.getByText('Prospective prediction evidence')).toBeTruthy())
    expect(screen.getByText(/AAA: no published predictive evidence/)).toBeTruthy()
    expect(screen.getByText('No prospectively validated evidence; cash retained.')).toBeTruthy()
    expect(screen.getByText('See full walk-forward validation and limitations')).toBeTruthy()
  })

})
