import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router'
import StartHerePage from './StartHerePage'

it('teaches the beginner route without implying a trade has occurred', () => {
  render(<MemoryRouter><StartHerePage /></MemoryRouter>)
  expect(screen.getByText('Understand stocks without the jargon')).toBeTruthy()
  expect(screen.getByText(/Saving a company does not buy anything/)).toBeTruthy()
  expect(screen.getByText(/no verified buy recommendations/i)).toBeTruthy()
  expect(screen.getByText('See the beginner stock-market dictionary')).toBeTruthy()
  expect(screen.getByRole('link', { name: 'See price history' }).getAttribute('href')).toBe('/history')
})

describe('plain-language navigation', () => {
  it('offers a simple guided path for new users', () => {
    render(<MemoryRouter><StartHerePage /></MemoryRouter>)
    expect(screen.getByRole('link', { name: 'Try an example' })).toBeTruthy()
  })
})
