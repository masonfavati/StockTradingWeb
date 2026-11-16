import { describe, expect, it } from 'vitest'
import { marketWords, plainPredictionStatus } from './marketWords'

describe('plain-language explanations', () => {
  it('provides a nonempty explanation for every displayed term', () => {
    for (const entry of Object.values(marketWords)) {
      expect(entry.label.length).toBeGreaterThan(2)
      expect(entry.explanation.length).toBeGreaterThan(35)
    }
  })
  it('never treats missing prediction evidence as success', () => {
    expect(plainPredictionStatus('insufficient_evidence')).toMatch(/Not enough/)
    expect(plainPredictionStatus('research_gate_passed')).toMatch(/not a guarantee/)
    expect(plainPredictionStatus('unexpected_status')).toBe('Not proven yet')
  })
})
