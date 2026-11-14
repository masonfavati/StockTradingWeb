import { fireEvent, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import { describe, expect, it } from 'vitest'
import App from './App'

function renderApp() {
  return render(
    <MemoryRouter initialEntries={['/']}>
      <App />
    </MemoryRouter>,
  )
}

describe('Application shell', () => {
  it('renders the dashboard', () => {
    renderApp()

    expect(
      screen.getByRole('heading', { name: 'Dashboard' }),
    ).toBeInTheDocument()
  })

  it('navigates to the portfolio', () => {
    renderApp()

    fireEvent.click(
      screen.getByRole('link', { name: 'Portfolio' }),
    )

    expect(
      screen.getByRole('heading', { name: 'Portfolio' }),
    ).toBeInTheDocument()
  })

  it('discloses that financial data is not connected', () => {
    renderApp()

    expect(
      screen.getByText('Data feeds not connected'),
    ).toBeInTheDocument()
  })
})
