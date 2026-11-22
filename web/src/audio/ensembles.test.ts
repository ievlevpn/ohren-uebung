import { describe, expect, it, test } from 'vitest'
import { ENSEMBLES, instrumentsFor, panFor } from './ensembles'

// Generated once from prep/fugue_prep/model.py (instruments_for, pan_for) for voices 1..5.
const INSTRUMENTS: Record<string, string[][]> = {
  chamber: [['flute'], ['flute', 'violin'], ['flute', 'violin', 'cello'], ['flute', 'violin', 'violin', 'cello'], ['flute', 'violin', 'violin', 'violin', 'cello']],
  harpsichord: [1, 2, 3, 4, 5].map((n) => Array(n).fill('harpsichord')),
  strings: [['violin'], ['violin', 'cello'], ['violin', 'violin', 'cello'], ['violin', 'violin', 'viola', 'cello'], ['violin', 'violin', 'viola', 'viola', 'cello']],
  organ: [1, 2, 3, 4, 5].map((n) => Array(n).fill('organ')),
}
const PANS: number[][] = [[0.0], [-0.6, 0.6], [-0.6, 0.0, 0.6], [-0.6, -0.2, 0.2, 0.6], [-0.6, -0.3, 0.0, 0.3, 0.6]]

describe('ensembles', () => {
  it('lists the four ensembles with their instrument tables', () => {
    expect(Object.keys(ENSEMBLES)).toEqual(['chamber', 'harpsichord', 'strings', 'organ'])
    expect(ENSEMBLES.chamber.instruments).toEqual(['flute', 'violin', 'cello'])
    expect(ENSEMBLES.strings.instruments).toEqual(['violin', 'violin', 'viola', 'cello'])
  })

  it('instrumentsFor matches the Python table for voices 1-5', () => {
    for (const [ens, rows] of Object.entries(INSTRUMENTS))
      rows.forEach((expected, i) => expect(instrumentsFor(ens, i + 1), `${ens} ${i + 1}`).toEqual(expected))
  })

  it('panFor matches the Python values for voices 1-5', () => {
    PANS.forEach((expected, i) => {
      const n = i + 1
      expected.forEach((p, v) => expect(panFor(v, n)).toBeCloseTo(p, 6))
    })
  })

  it('panFor spreads voices symmetrically', () => {
    for (let n = 2; n <= 6; n++) for (let v = 0; v < n; v++) expect(panFor(v, n)).toBeCloseTo(-panFor(n - 1 - v, n), 9)
    expect(panFor(0, 4)).toBe(-0.6)
    expect(panFor(3, 4)).toBe(0.6)
  })
})

test('a voice beyond its instrument moves to one of the ensemble that can play it', async () => {
  const { instrumentsForRanges } = await import('./ensembles')
  // strings, 4 voices: violin, violin, viola, cello — a tenor going down to A2 (45) cannot be a viola
  expect(instrumentsForRanges('strings', [[67, 84], [60, 79], [45, 64], [36, 60]])).toEqual(['violin', 'violin', 'cello', 'cello'])
  // everything fits: unchanged
  expect(instrumentsForRanges('strings', [[67, 84], [60, 79], [50, 70], [40, 60]])).toEqual(['violin', 'violin', 'viola', 'cello'])
  // organ only: a bass below C2 keeps the organ (no other instrument in the ensemble)
  expect(instrumentsForRanges('organ', [[60, 80], [34, 55]])).toEqual(['organ', 'organ'])
})
