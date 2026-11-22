import { expect, test } from 'vitest'
import { FINAL_HOLD, PLAIN, TUNINGS, accent, envelopeFor, impulse, roomLevel, tuningById, tuningFactor } from './shape'

const cents = (f: number) => 1200 * Math.log2(f)

test('equal temperament at 440 leaves every pitch alone', () => {
  for (let p = 36; p < 90; p++) expect(tuningFactor(p, tuningById('equal'))).toBeCloseTo(1, 12)
})

test('a′ 415 lowers a′ by a semitone (≈101 cents); a′ itself is the reference of each temperament', () => {
  expect(cents(tuningFactor(69, tuningById('vallotti')))).toBeCloseTo(-101.3, 1)
  for (const t of TUNINGS) expect(t.cents[9]).toBe(0)
})

test('Vallotti: the fifth C–G is narrowed, G♯–D♯ (A♭–E♭) is pure', () => {
  const t = tuningById('vallotti')
  const fifth = (a: number, b: number) => 700 + t.cents[b] - t.cents[a]
  expect(fifth(0, 7)).toBeCloseTo(698.0, 0) // tempered by ~1/6 comma
  expect(fifth(8, 3)).toBeCloseTo(701.9, 0) // pure
})

test('unknown tuning ids fall back to equal', () => {
  expect(tuningById('nope').id).toBe('equal')
})

test('plain playing keeps the old hard start and 0.08 s fade; shaped strings breathe', () => {
  expect(envelopeFor('violin', false)).toEqual(PLAIN)
  expect(envelopeFor('violin', true).attack).toBeGreaterThan(0)
  expect(envelopeFor('harpsichord', true).attack).toBe(0)
})

test('accents: first beat stronger, between beats lighter; keyboards have no dynamics', () => {
  expect(accent(0, 4, 0, 'flute')).toBe(1.15)
  expect(accent(5, 4, 0, 'flute')).toBe(1)
  expect(accent(5.5, 4, 0, 'flute')).toBe(0.9)
  expect(accent(1, 4, 1, 'violin')).toBe(1.15) // with a one-beat upbeat, bar 1 starts at beat 1
  expect(accent(0, 4, 0, 'harpsichord')).toBe(1)
  expect(accent(0, 4, 0, 'organ')).toBe(1)
  expect(FINAL_HOLD).toBeGreaterThan(1)
})

test('the room is lighter for harpsichord, fuller for organ', () => {
  expect(roomLevel(['harpsichord', 'harpsichord'])).toBeLessThan(roomLevel(['flute', 'cello']))
  expect(roomLevel(['organ'])).toBeGreaterThan(roomLevel(['flute', 'cello']))
})

test('the impulse decays to near silence and is deterministic', () => {
  const [l, r] = impulse(8000, 1)
  expect(l.length).toBe(r.length)
  const peak = (a: Float32Array, from: number, to: number) => a.slice(from, to).reduce((m, x) => Math.max(m, Math.abs(x)), 0)
  expect(peak(l, l.length - 400, l.length)).toBeLessThan(peak(l, 200, 600) / 100)
  expect(impulse(8000, 1)[0]).toEqual(l)
})
