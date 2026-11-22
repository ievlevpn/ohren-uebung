import { expect, test } from 'vitest'
import { isEmphasised } from '../render/techniques'
import { figureHeight, figureLayout, figureNow } from './figure'
import { exampleEnd, parseGlossary } from './model'
import glossaryText from '../../public/data/glossary.json?raw'

const glossary = parseGlossary(JSON.parse(glossaryText))
const examples = glossary.entries.flatMap(e => (e.example ? [e.example] : []))

test('a figure shows its whole example inside the frame, phone and desktop', () => {
  for (const ex of examples) {
    for (const width of [340, 560]) {
      const h = figureHeight(ex, width)
      const L = figureLayout(ex, width, h, 2)
      const now = figureNow(ex)
      expect(L.x(0, now)).toBeGreaterThanOrEqual(4)
      expect(L.x(exampleEnd(ex), now)).toBeLessThanOrEqual(width - 4)
      for (const n of ex.notes) {
        expect(L.y(n.p) - L.noteHeight / 2).toBeGreaterThanOrEqual(L.band.height - 1)
        expect(L.y(n.p) + L.noteHeight / 2).toBeLessThanOrEqual(h)
      }
      expect(h).toBeGreaterThanOrEqual(90)
      expect(h).toBeLessThanOrEqual(320)
    }
  }
})

test('a figure is drawn as after the music: every thread shown, no note emphasised as sounding', () => {
  for (const ex of examples) {
    const now = figureNow(ex)
    for (const t of ex.threads) expect(ex.notes[t.b].s).toBeLessThan(now)
    for (const n of ex.notes) {
      expect(n.s <= now && now < n.s + n.d).toBe(false)
      expect(isEmphasised(ex, n, now)).toBe(false)
    }
  }
})
