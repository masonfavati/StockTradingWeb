/** Public-facing explanations deliberately avoid investment jargon and promises. */
export const marketWords = {
  stock: {
    label: 'Stock',
    explanation: 'A small piece of ownership in a company. Its price can rise or fall, and you can lose the money you invest.',
  },
  ticker: {
    label: 'Stock symbol (ticker)',
    explanation: 'A short code used to find a stock. AAPL is one example. It is a name tag, not a rating.',
  },
  spy: {
    label: 'SPY',
    explanation: 'A fund that holds shares in many large U.S. companies. We use it as a familiar comparison, not as a guaranteed safe investment.',
  },
  fund: {
    label: 'Fund / ETF',
    explanation: 'An investment that holds a collection of things, often many different stocks. A fund can still lose value.',
  },
  cash: {
    label: 'Cash left over',
    explanation: 'The portion of your example budget not assigned to an investment. It has not been spent or invested by this website.',
  },
  adjusted: {
    label: 'Adjusted closing price',
    explanation: 'An old end-of-day share price changed to account for later events such as stock splits and dividends. It is useful for studying history, but is not a price you can buy at today.',
  },
  change: {
    label: 'Price change',
    explanation: 'How much the displayed price moved between the first and last dates shown, as a percentage. It does not tell you what comes next.',
  },
  daily: {
    label: 'Typical move between recorded days',
    explanation: 'The average size of the historical price moves between consecutive dates on this chart. Up and down both count. This is not a prediction or a worst-case loss.',
  },
  drop: {
    label: 'Biggest drop from a previous high',
    explanation: 'The largest fall in the displayed history from a previous high point to a later low point. A future fall could be much worse.',
  },
  index: {
    label: 'Compare starting at 100',
    explanation: 'Both lines are scaled to start at 100 so you can compare changes. The 100 is a made-up starting scale, not a stock price, dollar investment, or profit.',
  },
  risk: {
    label: 'Risk / price swings',
    explanation: 'Prices can move sharply and money can be lost. Historical price swings describe what happened before, not the size of possible future losses.',
  },
  correlation: {
    label: 'Moving together (correlation)',
    explanation: 'A number describing whether two investments tended to go up and down together in the past. Close to 1 means they often moved the same way, but that can change.',
  },
  sec: {
    label: 'SEC company match / CIK',
    explanation: 'A government filing reference helps match a stock symbol to a reporting company. CIK is that filer’s ID number. A match does not prove a stock is suitable to buy.',
  },
  sic: {
    label: 'Industry code / SIC',
    explanation: 'A government-reported label for a company’s main business type. Two companies with different codes can still have similar risks.',
  },
  scan: {
    label: 'Research scan',
    explanation: 'A search through stocks using facts about their earlier prices. Passing the scan does not mean a stock is likely to go up.',
  },
  prediction: {
    label: 'Prediction evidence',
    explanation: 'The app tests whether its earlier guesses actually worked in later real markets. Until enough tests pass, it does not treat those guesses as reliable or draw a future price line.',
  },
  forecast: {
    label: 'Beating SPY',
    explanation: 'Doing better than the SPY fund over the same period. A stock can beat SPY and still lose money when both prices fall.',
  },
  loss: {
    label: 'Example loss',
    explanation: 'A what-if calculation showing how the budget would change after a chosen price fall. It is not a prediction, guarantee, or maximum possible loss.',
  },
} as const

export type MarketWord = keyof typeof marketWords

export function plainPredictionStatus(status: string): string {
  if (status === 'research_gate_passed') return 'Passed research checks (not a guarantee)'
  if (status === 'insufficient_evidence') return 'Not enough real results yet'
  if (status === 'no_verified_outcomes') return 'Waiting for real results'
  if (status === 'not_available' || status === 'unavailable') return 'Not available right now'
  return 'Not proven yet'
}
