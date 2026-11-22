import { expect, test } from 'vitest'
import { parseGlossary } from '../glossary/model'
import type { Library } from '../model'
import { renderIndex } from './index'
import libraryText from '../../public/data/library.json?raw'
import glossaryText from '../../public/data/glossary.json?raw'

const library = JSON.parse(libraryText) as Library
const glossary = parseGlossary(JSON.parse(glossaryText))
const html = renderIndex(library, glossary)

test('the glossary runs alphabetically under letter heads, one article per entry', () => {
  const letters = [...html.matchAll(/<div class="letter">(.)<\/div>/g)].map(m => m[1])
  expect(letters).toEqual([...new Set(glossary.entries.map(e => e.title[0].toUpperCase()))])
  expect(letters).toEqual([...letters].sort())
  for (const e of glossary.entries) expect(html).toContain(`id="g-${e.id}"`)
  expect(html).toContain('<h2>Inversion <small>also: contrary motion · per motum contrarium · mirror</small></h2>')
})

test('each illustrated entry has a figure, its caption and a hear button', () => {
  const n = glossary.entries.filter(e => e.example).length
  expect(html.match(/<canvas/g)).toHaveLength(n)
  expect(html.match(/class="hear"/g)).toHaveLength(n)
  expect(html).toContain('The chromatic fourth, D down to A through every semitone.')
})

test('"hear it in" links each piece, "see also" links the related entries', () => {
  const stretto = html.slice(html.indexOf('id="g-stretto"'), html.indexOf('id="g-subject"'))
  expect(stretto).toContain('<b>Hear it in</b>')
  for (const id of library.techniques.stretto) expect(stretto).toContain(`href="#/p/${id}"`)
  expect(stretto).toContain('href="#/i/fugue"')
  const interval = html.slice(html.indexOf('id="g-canon-at-an-interval"'), html.indexOf('id="g-canon-at-the-unison"'))
  expect(interval).toMatch(/Variatio 12<\/a> <i>at the fourth<\/i>/)
})

test('a long "hear it in" shows six pieces, then "and N more" that opens in place', () => {
  const answer = html.slice(html.indexOf('id="g-answer"'), html.indexOf('id="g-augmentation"'))
  const n = glossary.entries.find(e => e.id === 'answer')!.pieces.length
  expect(n).toBeGreaterThan(6)
  const shown = answer.slice(0, answer.indexOf('<span class="rest"'))
  expect(shown.match(/href="#\/p\//g)).toHaveLength(6)
  expect(answer).toContain(`<button type="button" class="more" aria-expanded="false">and ${n - 6} more</button>`)
  expect(answer).toMatch(/<span class="rest" hidden>/)
  expect(answer.match(/href="#\/p\//g)).toHaveLength(n) // all linked, the rest hidden until asked
  const short = html.slice(html.indexOf('id="g-retrograde"'), html.indexOf('id="g-stretto"'))
  expect(short).not.toContain('class="more"')
})

test('the free passage entry lists pieces', () => {
  const free = html.slice(html.indexOf('id="g-free-passage"'), html.indexOf('id="g-fugue"'))
  expect(free).toContain('<b>Hear it in</b>')
})
