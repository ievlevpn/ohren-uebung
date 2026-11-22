import { expect, test } from 'vitest'
import type { Piece } from '../model'
import { layoutFor } from './layout'
import { MUTED_ALPHA, fade, threadFade, markFade } from './mute'
import { voiceAt } from './roll'

const piece: Piece = {
  id: 't', title: 't', collection: 'c', catalogue: '', key: '', tempo: 60, beatsPerBar: 4, ensemble: 'chamber',
  voices: [{ name: 'a', texture: 'solid', instrument: 'x', pan: 0 }, { name: 'b', texture: 'open', instrument: 'x', pan: 0 }],
  notes: [{ v: 0, p: 60, s: 0, d: 4 }, { v: 1, p: 67, s: 1, d: 2 }],
  threads: [{ a: 0, b: 1, kind: 'imitation', broken: false, adjusted: false }],
  marks: [{ kind: 'entry', start: 0, end: 4, voice: 1, label: 'subject' }, { kind: 'stretto', start: 0, end: 4 }],
  captions: [], techniques: [], listenFor: '',
}

test('muted voices are drawn at the faded alpha, others at full', () => {
  expect(MUTED_ALPHA).toBeCloseTo(0.25)
  const muted = new Set([1])
  expect(fade(muted, 1)).toBe(MUTED_ALPHA)
  expect(fade(muted, 0)).toBe(1)
  expect(fade(undefined, 1)).toBe(1)
})

test('a thread fades when either end is in a muted voice; entry marks by voice, voiceless marks never', () => {
  const muted = new Set([1])
  expect(threadFade(piece, piece.threads[0], muted)).toBe(MUTED_ALPHA)
  expect(threadFade(piece, piece.threads[0], new Set([0]))).toBe(MUTED_ALPHA)
  expect(threadFade(piece, piece.threads[0], new Set())).toBe(1)
  expect(markFade(piece.marks[0], muted)).toBe(MUTED_ALPHA)
  expect(markFade(piece.marks[0], new Set([0]))).toBe(1)
  expect(markFade(piece.marks[1], muted)).toBe(1)
})

test('voiceAt hits the drawn note rectangle, topmost first, and ignores empty paper', () => {
  const L = layoutFor(piece, 600, 300, 1)
  const now = 1
  // middle of note 1 (voice 1, beats 1..3)
  expect(voiceAt(piece, L, now, L.x(2, now), L.y(67))).toBe(1)
  expect(voiceAt(piece, L, now, L.x(0.5, now), L.y(60))).toBe(0)
  expect(voiceAt(piece, L, now, L.x(2, now), L.y(60) + 40)).toBeNull() // empty paper
  expect(voiceAt(piece, L, now, L.x(6, now), L.y(67))).toBeNull() // after the music
})

test('overlapping notes: the one drawn last (later in the list) wins', () => {
  const p = { ...piece, notes: [{ v: 0, p: 60, s: 0, d: 4 }, { v: 1, p: 60, s: 0, d: 4 }] }
  const L = layoutFor(p, 600, 300, 1)
  const hit = voiceAt(p, L, 0, L.x(2, 0), L.y(60))
  expect(hit).toBe(1)
})

test('voiceAt forgives a touch: the nearest note within 8 px, nothing 20 px away', () => {
  const p = { ...piece, notes: [{ v: 1, p: 67, s: 1, d: 0.01 }] } // a hairline note
  const L = layoutFor(p, 600, 300, 1)
  const x = L.x(1, 0), y = L.y(67)
  expect(voiceAt(p, L, 0, x + 5, y)).toBe(1)
  expect(voiceAt(p, L, 0, x + 20, y)).toBeNull()
  expect(voiceAt(p, L, 0, x, y - 20)).toBeNull()
})

test('voiceAt prefers an exact hit over a nearer-centre neighbour', () => {
  const p = { ...piece, notes: [{ v: 0, p: 60, s: 0, d: 4 }, { v: 1, p: 62, s: 0, d: 0.01 }] }
  const L = layoutFor(p, 600, 300, 1)
  expect(voiceAt(p, L, 0, L.x(2, 0), L.y(60))).toBe(0)
})

test('canvas density is capped at 2 (Pixel 2.625 → 2), never below 1', async () => {
  const { canvasDpr, FRAME_MS } = await import('./layout')
  expect(canvasDpr(2.625)).toBe(2)
  expect(canvasDpr(3)).toBe(2)
  expect(canvasDpr(1.5)).toBe(1.5)
  expect(canvasDpr(undefined)).toBe(1)
  expect(1000 / FRAME_MS).toBeLessThanOrEqual(62)
})
