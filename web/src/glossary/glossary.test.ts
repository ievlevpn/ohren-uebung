import { expect, test } from 'vitest'
import type { Library } from '../model'
import { entryFor, exampleEnd, parseGlossary } from './model'
import libraryText from '../../public/data/library.json?raw'
import glossaryText from '../../public/data/glossary.json?raw'
import samplesText from '../../public/samples/index.json?raw'

const library = JSON.parse(libraryText) as Library
const glossary = parseGlossary(JSON.parse(glossaryText))
const samples = JSON.parse(samplesText) as Record<string, number[]>

test('glossary.json validates: entries in alphabetical order, examples shaped like pieces', () => {
  const titles = glossary.entries.map(e => e.title)
  expect(titles).toEqual([...titles].sort((a, b) => a.localeCompare(b)))
  expect(glossary.entries.length).toBeGreaterThanOrEqual(15)
  for (const e of glossary.entries) {
    expect(e.text.length).toBeGreaterThan(e.short.length)
    if (!e.example) continue
    expect(e.example.notes.length).toBeGreaterThan(0)
    expect(exampleEnd(e.example)).toBeGreaterThan(0)
    for (const t of e.example.threads) expect(e.example.notes[t.b].s).toBeGreaterThanOrEqual(e.example.notes[t.a].s)
  }
  expect(() => parseGlossary({ entries: 'no' })).toThrow()
})

test('every library technique opens exactly one glossary entry', () => {
  for (const t of Object.keys(library.techniques)) {
    const e = entryFor(glossary, t)
    expect(e, t).toBeDefined()
    expect(e!.aliases).toContain(t.toLowerCase())
  }
  expect(entryFor(glossary, 'Contrary motion')?.id).toBe('inversion')
  expect(entryFor(glossary, 'crab')?.id).toBe('retrograde')
  expect(entryFor(glossary, 'nonsense')).toBeUndefined()
  for (const e of glossary.entries) for (const a of e.links) expect(e.aliases).toContain(a)
  expect(glossary.entries.flatMap(e => e.links)).not.toContain('round')
  expect(glossary.entries.flatMap(e => e.links)).not.toContain('cadence')
})

test('"hear it in" lists exactly the pieces whose techniques map to the entry', () => {
  for (const e of glossary.entries) {
    expect(e.pieces.length, e.id).toBeGreaterThan(0)
    if (e.id === 'free-passage') continue // generated from the markings' free ranges and codas
    const want = new Set(Object.entries(library.techniques)
      .filter(([t]) => entryFor(glossary, t) === e).flatMap(([, ids]) => ids))
    expect(new Set(e.pieces.map(p => p.id)), e.id).toEqual(want)
  }
})

test('every example plays within 3 semitones of a sample of its instrument', () => {
  for (const e of glossary.entries) {
    if (!e.example) continue
    for (const n of e.example.notes) {
      const avail = samples[e.example.voices[n.v].instrument]
      expect(avail, e.id).toBeDefined()
      expect(Math.min(...avail.map(m => Math.abs(m - n.p))), `${e.id} ${n.p}`).toBeLessThanOrEqual(3)
    }
  }
})
