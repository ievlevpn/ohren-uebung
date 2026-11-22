import { expect, test } from 'vitest'
import type { Mark, Note, Piece } from '../model'
import { barOf, parsePiece } from '../model'
import { layoutFor } from './layout'
import { adjustedTick, derive, drawAnnotations, isEmphasised, labelAt, mirrorAxisY, railPointer, subjectOf, subjectOpenings, type LabelHit } from './techniques'
import { unisonOffsets } from './roll'
import motumText from '../../public/data/pieces/bwv1079-motum-contrarium.json?raw'
import fugueText from '../../public/data/pieces/bwv847.json?raw'
import inv3Text from '../../public/data/pieces/invention03.json?raw'
import inv1Text from '../../public/data/pieces/invention01.json?raw'
import tripleText from '../../public/data/pieces/bwv849.json?raw'

test('mirror axis lies strictly between the two rows of a mirrored pair', () => {
  const piece = parsePiece(JSON.parse(motumText))
  const axis = piece.marks.find(m => m.kind === 'mirror-axis')!
  const L = layoutFor(piece, 390, 560, 3)
  const y = mirrorAxisY(L, axis.pitch!)
  // e♭' (63) and e' (64) mirror onto each other; so do c' (60) and g' (67)
  for (const [lo, hi] of [[63, 64], [60, 67]]) {
    expect(y).toBeLessThan(L.y(lo))
    expect(y).toBeGreaterThan(L.y(hi))
    expect(y - L.y(hi)).toBeCloseTo(L.y(lo) - y)
  }
})

test('rail pointer names the opening subject and its bar once it is off screen', () => {
  const first: Mark = { kind: 'entry', start: 16.5, end: 24, voice: 1, label: 'subject' }
  expect(railPointer(first, 4, 120)).toBeNull()
  expect(railPointer(first, 4, 0)).toBeNull()
  expect(railPointer(first, 4, -300)).toBe('☜ subject, bar 5')
  expect(railPointer({ ...first, start: 0, label: undefined }, 3, -1)).toBe('☜ subject, bar 1')
})

test('rail pointer counts bars from the end of an upbeat', () => {
  // 3 beats a bar after a 1-beat upbeat: bar n starts at 1 + 3(n - 1)
  const at = (start: number) => railPointer({ kind: 'entry', start, end: start + 4, label: 'motive' }, 3, -1, 1)
  expect(at(0)).toBe('☜ motive, upbeat')
  expect(at(1)).toBe('☜ motive, bar 1')
  expect(at(6)).toBe('☜ motive, bar 2')   // the last eighth of bar 2
  expect(at(7)).toBe('☜ motive, bar 3')
})

test('inventions name their motive; Invention 3 keeps its upbeat', () => {
  const inv1 = parsePiece(JSON.parse(inv1Text))
  const first1 = inv1.marks.find(m => m.kind === 'entry')!
  expect(railPointer(first1, inv1.beatsPerBar, -1, inv1.pickup)).toBe('☜ motive, bar 1')
  const inv3 = parsePiece(JSON.parse(inv3Text))
  expect(inv3.pickup).toBe(1)
  const entries = inv3.marks.filter(m => m.kind === 'entry')
  expect(entries.every(m => m.label === 'motive')).toBe(true)
  expect(railPointer(entries[1], inv3.beatsPerBar, -1, inv3.pickup)).toBe('☜ motive, bar 2')
  expect(barOf(inv3, entries[2].start)).toBe(12)
  expect(barOf(parsePiece(JSON.parse(fugueText)), 8.5)).toBe(3)  // no upbeat: as before
})

test('entry notes are emphasised only once they have started', () => {
  const piece: Piece = parsePiece(JSON.parse(fugueText))
  const answer = piece.marks.filter(m => m.kind === 'entry')[1]
  const notes = piece.notes.filter(n => n.v === answer.voice && n.s >= answer.start && n.s < answer.end)
  const now = notes[2].s
  expect(isEmphasised(piece, notes[0], now)).toBe(true)
  expect(isEmphasised(piece, notes[2], now)).toBe(true)   // sounding
  expect(isEmphasised(piece, notes[3], now)).toBe(false)  // still to come
  // the alto's free counterpoint after its subject (no entry) is never emphasised
  const outside = piece.notes.find(n => n.v === 1 && n.s >= 8.25 && n.s <= now)!
  expect(isEmphasised(piece, outside, now)).toBe(false)
})

test('entry emphasis ends one beat after the entry stops sounding', () => {
  const piece: Piece = parsePiece(JSON.parse(fugueText))
  const answer = piece.marks.filter(m => m.kind === 'entry')[1]
  const first = piece.notes.find(n => n.v === answer.voice && n.s >= answer.start && n.s < answer.end)!
  expect(isEmphasised(piece, first, answer.end - 0.01)).toBe(true)
  expect(isEmphasised(piece, first, answer.end + 0.99)).toBe(true)
  expect(isEmphasised(piece, first, answer.end + 1)).toBe(false)
  expect(isEmphasised(piece, first, answer.end + 20)).toBe(false)
})

function tiny(notes: Note[]): Piece {
  return {
    id: 't', title: 'T', collection: 'c', catalogue: '', key: 'C', tempo: 60, beatsPerBar: 4, ensemble: 'chamber',
    voices: [0, 1, 2].map(i => ({ name: `V${i}`, texture: 'solid' as const, instrument: 'x', pan: 0 })),
    notes, threads: [], marks: [], captions: [], techniques: [], listenFor: '',
  }
}

test('an adjusted thread gets a small tick just before its follower note, across the thread', () => {
  const piece = tiny([{ v: 0, p: 60, s: 0, d: 1 }, { v: 1, p: 68, s: 2, d: 1 }])
  const L = layoutFor(piece, 390, 560, 2)
  const b = piece.notes[1]
  const t = adjustedTick(L, b, 2)
  const left = L.x(b.s, 2)
  // left of the note, close to it, never inside it
  expect(Math.max(t.x0, t.x1)).toBeLessThan(left)
  expect(Math.min(t.x0, t.x1)).toBeGreaterThan(left - 10)
  // a short oblique stroke crossing the follower's row
  expect(Math.min(t.y0, t.y1)).toBeLessThan(L.y(b.p))
  expect(Math.max(t.y0, t.y1)).toBeGreaterThan(L.y(b.p))
  expect(Math.hypot(t.x1 - t.x0, t.y1 - t.y0)).toBeLessThan(9)
  expect(t.x0).not.toBe(t.x1)
})

test('unisons: notes of different voices on one pitch at once are split up and down the row', () => {
  const notes: Note[] = [
    { v: 0, p: 65, s: 0, d: 2 },
    { v: 1, p: 65, s: 1, d: 2 }, // overlaps voice 0 on F
    { v: 2, p: 65, s: 4, d: 1 }, // same pitch, later: no overlap
    { v: 0, p: 67, s: 2, d: 1 },
    { v: 0, p: 67, s: 3, d: 1 }, // same voice repeated: not a unison
  ]
  const off = unisonOffsets(tiny(notes))
  expect(off.get(notes[0])).toBeLessThan(0) // upper voice: raised, its top stays in view
  expect(off.get(notes[1])).toBeGreaterThan(0)
  expect(Math.abs(off.get(notes[0])! - off.get(notes[1])!)).toBeLessThanOrEqual(0.5)
  expect(off.has(notes[2])).toBe(false)
  expect(off.has(notes[3])).toBe(false)
  expect(off.has(notes[4])).toBe(false)
})

test('secondary notes (lower chord tones, split-off lines) are never part of an entry', () => {
  const notes: Note[] = [
    { v: 0, p: 60, s: 0, d: 1 }, { v: 0, p: 55, s: 0, d: 1, c: true }, { v: 0, p: 62, s: 1, d: 1 },
  ]
  const piece = parsePiece({
    id: 't', title: 't', collection: 'wtc', catalogue: '', key: '', ensemble: 'harpsichord', listenFor: '',
    tempo: 60, beatsPerBar: 4, voices: [{ name: 'S', texture: 'solid', instrument: 'harpsichord', pan: 0 }],
    notes, threads: [], captions: [], techniques: [],
    marks: [{ kind: 'entry', start: 0, end: 2, voice: 0, label: 'subject' }],
  })
  expect(isEmphasised(piece, notes[0], 0.5)).toBe(true)
  expect(isEmphasised(piece, notes[1], 0.5)).toBe(false)
})

test('a statement of the subject\'s head alone is drawn with its own label and spans only the head', () => {
  const notes: Note[] = [
    { v: 0, p: 60, s: 0, d: 1 }, { v: 0, p: 62, s: 1, d: 1 },
    { v: 1, p: 67, s: 2, d: 1 }, { v: 1, p: 69, s: 3, d: 1 }, { v: 1, p: 50, s: 4, d: 4 },
  ]
  const piece = parsePiece({
    id: 't', title: 't', collection: 'wtc', catalogue: '', key: '', ensemble: 'harpsichord', listenFor: '',
    tempo: 60, beatsPerBar: 4, notes, threads: [], captions: [], techniques: [],
    voices: [{ name: 'S', texture: 'solid', instrument: 'harpsichord', pan: 0 },
             { name: 'A', texture: 'hatch', instrument: 'harpsichord', pan: 0 }],
    marks: [{ kind: 'entry', start: 0, end: 2, voice: 0, label: 'subject' },
            { kind: 'entry', start: 2, end: 4, voice: 1, label: 'answer (head)' }],
  })
  const texts: string[] = []
  const ctx = new Proxy({}, {
    get: (_t, k) => k === 'fillText' ? (t: string) => { texts.push(t) }
      : k === 'measureText' ? (t: string) => ({ width: t.length * 5 })
      : () => undefined,
    set: () => true,
  }) as unknown as CanvasRenderingContext2D
  drawAnnotations(ctx, piece, layoutFor(piece, 1200, 500, 1), 3)
  expect(texts).toContain('answer (head)')
  expect(isEmphasised(piece, notes[3], 3.5)).toBe(true)
  expect(isEmphasised(piece, notes[4], 6)).toBe(false) // after the head: not the entry's
})

test('every label drawn is recorded with its box and its mark, for taps', () => {
  const piece = parsePiece(JSON.parse(motumText))
  const L = layoutFor(piece, 1200, 500, 1)
  const ctx = new Proxy({}, {
    get: (_t, k) => k === 'measureText' ? (t: string) => ({ width: t.length * 5 }) : () => undefined,
    set: () => true,
  }) as unknown as CanvasRenderingContext2D
  const hits: LabelHit[] = []
  drawAnnotations(ctx, piece, L, 10, undefined, hits)
  const axis = piece.marks.find(m => m.kind === 'mirror-axis')!
  const h = hits.find(x => x.mark === axis)!
  expect(h.text).toBe("e♭'")
  expect(h.w).toBe(h.text.length * 5)
  expect(h.y + h.h).toBeGreaterThan(mirrorAxisY(L, axis.pitch!) - 3.5)
})

test('a tap finds a label within a 44 px target, the nearest when two are close', () => {
  const a = { x: 100, y: 20, w: 40, h: 11, text: 'subject', mark: null }
  const b = { x: 100, y: 33, w: 40, h: 11, text: 'answer', mark: null }
  expect(labelAt([a, b], 120, 25)).toBe(a)
  expect(labelAt([a, b], 120, 40)).toBe(b)
  expect(labelAt([a], 120, 25 + 21)).toBe(a)      // 44 px tall around the lettering
  expect(labelAt([a], 120, 25 + 24)).toBeNull()
  expect(labelAt([a], 100 - 3, 25)).toBe(a)       // a little beyond the ends
  expect(labelAt([], 0, 0)).toBeNull()
})

test('each subject of a fugue on several subjects has its own opening on the rail', () => {
  expect(subjectOf('subject II')).toBe('II')
  expect(subjectOf('answer III inverted')).toBe('III')
  expect(subjectOf('subject I (head)')).toBe('I')
  expect(subjectOf('subject')).toBeNull()
  expect(subjectOf('subject inverted')).toBeNull()
  expect(subjectOf(undefined)).toBeNull()
  // BWV 849: subjects I, II, III first heard in bars 1, 36 and 49
  const triple = parsePiece(JSON.parse(tripleText))
  const openings = [...derive(triple).openings].map(m => [m.label, barOf(triple, m.start)])
  expect(openings).toEqual([['subject I', 1], ['subject II', 36], ['subject III', 49]])
  // a one-subject fugue: only its first entry
  const one = parsePiece(JSON.parse(fugueText))
  const entries = one.marks.filter(m => m.kind === 'entry').sort((a, b) => a.start - b.start)
  expect([...subjectOpenings(entries)]).toEqual([entries[0]])
  expect(subjectOpenings([]).size).toBe(0)
})
