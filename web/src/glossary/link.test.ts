import { expect, test } from 'vitest'
import type { Mark, Piece } from '../model'
import { parsePiece } from '../model'
import { parseGlossary } from './model'
import { findTerms, isCanon, labelEntries, linkHtml } from './link'
import glossaryText from '../../public/data/glossary.json?raw'

const g = parseGlossary(JSON.parse(glossaryText))
const pieces = Object.values(import.meta.glob('../../public/data/pieces/*.json', {
  eager: true, query: '?raw', import: 'default',
}) as Record<string, string>).map(t => parsePiece(JSON.parse(t)))
const piece = (id: string) => pieces.find(p => p.id === id)!

const found = (text: string) => findTerms(text, g).map(h => [text.slice(h.start, h.end), h.entry])

test('finds technique words by their linkable aliases, plurals too, any case', () => {
  expect(found('☞ Comes: by contrary motion, at the lower fifth, after one bar.'))
    .toEqual([['Comes', 'canon'], ['contrary motion', 'inversion']])
  expect(found('☞ Two strettos, then the subject inverted.'))
    .toEqual([['strettos', 'stretto'], ['subject', 'subject'], ['inverted', 'inversion']])
})

test('the longest alias wins: a canon at the fourth is one term, not "canon"', () => {
  expect(found('a canon at the fourth')).toEqual([['canon at the fourth', 'canon-at-an-interval']])
  expect(found('the tonal answer')).toEqual([['tonal answer', 'answer']])
  expect(found('dux and comes')).toEqual([['dux and comes', 'canon']])
})

test('never inside another word', () => {
  for (const t of ['It becomes clear.', 'It was answered.', 'a mirrored line', 'canonic writing',
    'fugal texture', 'subjective', 'the dux-like line', 'pre-canon', 'resubject']) {
    expect(found(t), t).toEqual([])
  }
})

test('only `links`: aliases that are also ordinary words are never linked', () => {
  for (const t of ['nearly four times round', 'leaps to a half cadence', 'the coda', 'an episode',
    'a free passage', 'free voices']) {
    expect(found(t), t).toEqual([])
  }
})

test('every occurrence is weighed: ordinary phrases and verb uses are skipped, the technical one is not', () => {
  // the guard's cases (prep/tests/test_glossary.py unsafe_uses)
  for (const t of ['The theme comes back in the bass.', 'Then it comes in, softly.', 'The tune comes round again.',
    'Here it comes: the dux.', 'The violin will answer it.', 'The alto answers them at once.',
    'Free voices answer it.', 'The bass waits to answer.', 'The voices mirror each other.']) {
    expect(found(t).filter(([w]) => w !== 'dux'), t).toEqual([])
  }
  expect(found('☞ The answer in the alto; then the soprano will answer it.'))
    .toEqual([['answer', 'answer']])
  // an `ordinary` phrase excuses only its own span
  const t = 'The violin answers it; the answer comes in the bass.'
  expect(findTerms(t, g).map(h => h.start)).toEqual([t.indexOf('answer comes') ])
  expect(found('a running answer')).toEqual([])
})

test('the real captions: the ordinary uses Task 1 found stay plain', () => {
  const perpetuo = piece('bwv1079-canone-perpetuo').captions[0].text
  expect(perpetuo).toContain('will answer it')
  expect(found(perpetuo)).toEqual([])
  expect(found(piece('invention12').listenFor).map(([w]) => w)).not.toContain('answer')
  const round = piece('bwv1079-thema-regium').captions[2].text
  expect(round).toContain('four times round')
  expect(found(round)).toEqual([['canon', 'canon']])
})

test('in every text of every piece, each term is a whole linkable alias outside the ordinary phrases', () => {
  const word = /[\p{L}\p{N}_-]/u
  let n = 0
  for (const p of pieces) {
    const texts = [...p.captions.map(c => c.text), p.listenFor, ...p.marks.flatMap(m => m.label ? [m.label] : [])]
    for (const t of texts) {
      const covered = g.ordinary.flatMap(o => [...t.toLowerCase().matchAll(new RegExp(o, 'g'))].map(m => [m.index!, m.index! + o.length]))
      for (const h of findTerms(t, g)) {
        n++
        const e = g.entries.find(x => x.id === h.entry)!
        const w = t.slice(h.start, h.end).toLowerCase()
        expect(e.links.includes(w) || e.links.includes(w.replace(/s$/, '')), `${p.id}: ${w}`).toBe(true)
        expect(word.test(t[h.start - 1] ?? ' ') || word.test(t[h.end] ?? ' '), `${p.id}: ${t}`).toBe(false)
        expect(covered.some(([lo, hi]) => h.start < hi && lo < h.end), `${p.id}: ${t}`).toBe(false)
      }
    }
  }
  expect(n).toBeGreaterThan(500)
})

test('linkHtml escapes the text and makes the first use of each entry a button', () => {
  const html = linkHtml('☞ Comes <i>: the comes by contrary motion & the dux.', g)
  expect(html).toBe('☞ <button type="button" class="term" data-entry="canon" data-term="Comes">Comes</button> &lt;i&gt;: ' +
    'the comes by <button type="button" class="term" data-entry="inversion" data-term="contrary motion">contrary motion</button> &amp; the dux.')
  expect(linkHtml('nothing here', g)).toBe('nothing here')
})

test('a label on the roll opens the entries it names, in order', () => {
  const entry = (label: string): Mark => ({ kind: 'entry', start: 0, end: 4, voice: 0, label })
  const fugue = piece('bwv847')
  expect(labelEntries(entry('subject'), 'subject', fugue, g)).toEqual(['subject'])
  expect(labelEntries(entry('answer inverted diminished'), 'answer inverted diminished', fugue, g))
    .toEqual(['answer', 'inversion', 'diminution'])
  expect(labelEntries(entry('subject augmented'), 'subject augmented', fugue, g)).toEqual(['subject', 'augmentation'])
  expect(labelEntries(entry('motive (head)'), '☜ motive, bar 1', fugue, g)).toEqual(['motive'])
  // a fugue on several subjects: the label also opens the double/triple fugue card
  expect(labelEntries(entry('answer II inverted'), 'answer II inverted', fugue, g))
    .toEqual(['answer', 'double-fugue', 'inversion'])
  const motum = piece('bwv1079-motum-contrarium')
  const axis = motum.marks.find(m => m.kind === 'mirror-axis')!
  expect(labelEntries(axis, "e♭'", motum, g)).toEqual(['inversion'])
  const tonos = piece('bwv1079-per-tonos')
  expect(labelEntries(tonos.marks[0], 'C minor', tonos, g)).toEqual(['per-tonos'])
  const crab = piece('bwv1079-cancrizans')
  expect(labelEntries(crab.marks[0], '← cancrizans →', crab, g)).toEqual(['retrograde'])
  const stretto: Mark = { kind: 'stretto', start: 0, end: 4, label: 's1' }
  expect(labelEntries(stretto, 'stretto', fugue, g)).toEqual(['stretto'])
  const aug = piece('bwv1079-augmentationem')
  expect(labelEntries(aug.marks.find(m => m.kind === 'stretch')!, '×2', aug, g)).toEqual(['augmentation'])
})

test('a stretch bracket is a diminution when the follower is quicker', () => {
  const p: Piece = {
    ...piece('bwv1079-augmentationem'),
    notes: [{ v: 0, p: 60, s: 0, d: 2 }, { v: 1, p: 60, s: 1, d: 1 }],
    threads: [{ a: 0, b: 1, kind: 'stretch', broken: false, adjusted: false }],
  }
  expect(labelEntries({ kind: 'stretch', start: 0, end: 4, voice: 1, label: '×½' }, '×½', p, g)).toEqual(['diminution'])
})

test('every "In this piece" note can be reached: its entry is linked somewhere in its piece', () => {
  const withNotes = pieces.filter(p => p.glossaryNotes)
  expect(withNotes.length).toBeGreaterThan(5)
  for (const p of withNotes) {
    const reach = new Set([
      ...[...p.captions.map(c => c.text), p.listenFor].flatMap(t => findTerms(t, g).map(h => h.entry)),
      ...p.marks.flatMap(m => labelEntries(m, m.label ?? '', p, g)),
    ])
    for (const id of Object.keys(p.glossaryNotes!)) expect(reach.has(id), `${p.id}: ${id}`).toBe(true)
  }
})

// ---- fix round 1: words that mean something else in their piece ----

/** Every word the library links, by kind of piece, and the entry it must open. A new linked word
 * (or a word opening another entry) fails here until it is added, after checking its meaning. */
const PINNED: Record<'canon' | 'other', Record<string, string>> = {
  canon: {
    augmentation: 'augmentation', cancrizans: 'retrograde', canon: 'canon', comes: 'canon', dux: 'canon',
    'canon at the second': 'canon-at-an-interval', 'canon at the third': 'canon-at-an-interval',
    'canon at the fourth': 'canon-at-an-interval', 'canon at the fifth': 'canon-at-an-interval',
    'canon at the sixth': 'canon-at-an-interval', 'canon at the seventh': 'canon-at-an-interval',
    'canon at the octave': 'canon-at-an-interval', 'canon at the ninth': 'canon-at-an-interval',
    'canon at the unison': 'canon-at-the-unison', 'contrary motion': 'inversion', 'crab canon': 'retrograde',
    'canon at the tenth': 'canon-at-an-interval', 'canon at the twelfth': 'canon-at-an-interval',
    inverted: 'inversion', mirror: 'inversion',
  },
  other: {
    answer: 'answer', augmentation: 'augmentation', chromatic: 'chromaticism', comes: 'answer',
    countermotive: 'motive', countersubject: 'countersubject', diminution: 'diminution', diminutions: 'diminution',
    dux: 'subject', exposition: 'fugue', fugue: 'fugue', inversion: 'inversion', inverted: 'inversion',
    mirror: 'inversion', motive: 'motive', motives: 'motive', stretto: 'stretto', strettos: 'stretto', subject: 'subject', subjects: 'subject',
    'mirror fugue': 'mirror-fugue', rectus: 'mirror-fugue', inversus: 'mirror-fugue',
    'double fugue': 'double-fugue', 'triple fugue': 'double-fugue',
  },
}

test('every linked word in the library opens the entry pinned for its kind of piece', () => {
  const wrong: string[] = []
  for (const p of pieces) {
    const kind = isCanon(p, g) ? 'canon' : 'other'
    const texts = [...p.captions.map(c => c.text), p.listenFor, ...p.marks.flatMap(m => m.label ? [m.label] : [])]
    for (const t of texts) {
      for (const h of findTerms(t, g, p)) {
        const w = t.slice(h.start, h.end).toLowerCase()
        if (PINNED[kind][w] !== h.entry) wrong.push(`${p.id}: "${w}" -> ${h.entry} in "${t}"`)
      }
    }
  }
  expect(wrong).toEqual([])
})

test('in a fugue, Dux and Comes open Subject and Answer, never Canon', () => {
  const fugues = pieces.filter(p => p.techniques.includes('fugue'))
  expect(fugues.length).toBe(42) // 24 WTC, 16 Art of Fugue, 2 ricercars
  for (const p of fugues) {
    expect(isCanon(p, g), p.id).toBe(false)
    for (const t of [...p.captions.map(c => c.text), p.listenFor]) {
      for (const h of findTerms(t, g, p)) expect(h.entry, `${p.id}: ${t}`).not.toBe('canon')
    }
  }
  const dux = piece('bwv846').captions.find(c => c.text.startsWith('☞ Dux:'))!.text
  expect(findTerms(dux, g, piece('bwv846'))[0].entry).toBe('subject')
  const comes = piece('contrapunctus01').captions.find(c => c.text.startsWith('☞ Comes:'))!.text
  expect(findTerms(comes, g, piece('contrapunctus01'))[0].entry).toBe('answer')
  // in a canon they stay the canon's names
  const motum = piece('bwv1079-motum-contrarium')
  expect(findTerms(motum.captions[1].text, g, motum)[0].entry).toBe('canon')
})

test('"answer" the verb is never linked, only the noun', () => {
  const mustNot = [
    ['goldberg-var24', 'The upper voice answers an octave higher.'],
    ['goldberg-var24', 'The middle voice answers an octave lower, two bars later.'],
    ['invention04', 'The lower voice answers with the motive an octave lower.'],
    ['invention07', 'The lower voice answers with the motive an octave lower.'],
  ]
  for (const [id, words] of mustNot) {
    const p = piece(id)
    const t = p.captions.map(c => c.text).find(x => x.includes(words))
    expect(t, `${id}: ${words}`).toBeDefined()
    expect(findTerms(t!, g, p).map(h => t!.slice(h.start, h.end).toLowerCase()), t).not.toContain('answers')
  }
  for (const t of ['☞ The answer in the alto.', '☞ Answer: on G.', 'its answer', "the subject's answer", 'a tonal answer', 'answer (head)']) {
    expect(findTerms(t, g).map(h => h.entry), t).toContain('answer')
  }
  for (const t of ['The tenor answers with the subject.', 'The bass answers on D.']) expect(findTerms(t, g).map(h => h.entry), t).not.toContain('answer')
})
