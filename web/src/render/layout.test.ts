import { expect, test } from 'vitest'
import type { Note, Piece } from '../model'
import { layoutFor } from './layout'

/** A four-voice piece spread over four and a half octaves (C2..F#6), one bar per voice. */
function fourVoices(): Piece {
  const ranges = [[72, 90], [60, 74], [48, 62], [36, 50]]
  const notes: Note[] = []
  ranges.forEach(([lo, hi], v) => {
    for (let p = lo, s = 0; p <= hi; p++, s += 0.5) notes.push({ v, p, s, d: 0.5 })
  })
  notes.sort((a, b) => a.s - b.s || a.v - b.v)
  return {
    id: 't', title: 'T', collection: 'c', catalogue: '', key: 'C', tempo: 72, beatsPerBar: 4,
    ensemble: 'chamber',
    voices: ['Soprano', 'Alto', 'Tenor', 'Bass'].map((name, i) => ({
      name, texture: (['solid', 'hatch', 'stipple', 'dashed'] as const)[i], instrument: 'x', pan: 0,
    })),
    notes, threads: [],
    marks: [
      { kind: 'entry', start: 0, end: 8, voice: 1, label: 'subject' },
      { kind: 'entry', start: 4, end: 12, voice: 0, label: 'answer' },
      { kind: 'stretto', start: 0, end: 12, label: '1' },
    ],
    captions: [], techniques: [], listenFor: '',
  }
}

test('portrait phone keeps notes at least 6px tall', () => {
  const piece = fourVoices()
  const L = layoutFor(piece, 390, 560, 3)
  expect(L.noteHeight).toBeGreaterThanOrEqual(6)
  // and every pitch still lands inside the canvas
  for (const n of piece.notes) {
    expect(L.y(n.p) - L.noteHeight / 2).toBeGreaterThanOrEqual(0)
    expect(L.y(n.p) + L.noteHeight / 2).toBeLessThanOrEqual(560)
  }
  // higher pitch is drawn higher
  expect(L.y(80)).toBeLessThan(L.y(40))
})

test('x of now is the playhead', () => {
  const piece = fourVoices()
  const phone = layoutFor(piece, 390, 560, 3)
  expect(phone.x(17.25, 17.25)).toBeCloseTo(390 * 0.4)
  expect(phone.x(18.25, 17.25)).toBeCloseTo(390 * 0.4 + phone.beatWidth)
  const wide = layoutFor(piece, 1000, 400, 2)
  expect(wide.x(3, 3)).toBeCloseTo(500)
  expect(wide.x(2, 3)).toBeCloseTo(500 - wide.beatWidth)
})
