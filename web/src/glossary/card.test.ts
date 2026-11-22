import { afterEach, expect, test, vi } from 'vitest'
import { parsePiece } from '../model'
import { parseGlossary } from './model'
import { cardHtml, createCard } from './card'
import glossaryText from '../../public/data/glossary.json?raw'
import motumText from '../../public/data/pieces/bwv1079-motum-contrarium.json?raw'

const g = parseGlossary(JSON.parse(glossaryText))
const entry = (id: string) => g.entries.find(e => e.id === id)!
const motum = parsePiece(JSON.parse(motumText))

afterEach(() => { vi.unstubAllGlobals() })

test('the card: title with the tapped word, the short definition, figure, hear, and a way to the glossary', () => {
  const html = cardHtml({ entry: entry('inversion'), term: 'contrary motion', others: [] })
  expect(html).toContain('<h3 id="gcard-title">Inversion <span class="term-used">· contrary motion</span></h3>')
  expect(html).toContain(`<p class="def">${entry('inversion').short}</p>`)
  expect(html).toContain('<canvas')
  expect(html).toContain('class="hear"')
  expect(html).toContain('<button type="button" class="close" aria-label="Close">✕</button>')
  expect(html).toContain('href="#/i/inversion"')
  expect(html).toContain('more in the glossary')
  expect(html).not.toContain('In this piece')
})

test('the tapped word is not repeated when it is the title, any case', () => {
  const html = cardHtml({ entry: entry('stretto'), term: 'Stretto', others: [] })
  expect(html).toContain('<h3 id="gcard-title">Stretto</h3>')
})

test('"In this piece" appears when the piece has a note for that entry', () => {
  expect(motum.glossaryNotes?.inversion).toBe('The comes mirrors the dux about E♭ — watch the dashed line.')
  const html = cardHtml({ entry: entry('inversion'), note: motum.glossaryNotes!.inversion, others: [] })
  expect(html).toContain('<div class="where here"><b>In this piece</b>The comes mirrors the dux about E♭ — watch the dashed line.</div>')
})

test('an entry without an illustration has no figure; a label naming several entries offers the others', () => {
  const html = cardHtml({ entry: entry('subject'), others: [entry('inversion'), entry('diminution')] })
  const inv = cardHtml({ entry: entry('invention'), others: [] })
  expect(inv).not.toContain('<canvas')
  expect(html).toContain('<b>Also here</b><button type="button" class="other" data-entry="inversion">Inversion</button>')
  expect(html).toContain('data-entry="diminution">Diminution</button>')
})

// ---- open and close, with a stand-in for the DOM (the tests run without one) ----

type Fn = (e: unknown) => void
function fakeDom() {
  const docListeners = new Map<string, Fn>()
  vi.stubGlobal('document', {
    addEventListener: (k: string, f: Fn) => docListeners.set(k, f),
    removeEventListener: (k: string, f: Fn) => { if (docListeners.get(k) === f) docListeners.delete(k) },
    activeElement: null,
  })
  vi.stubGlobal('window', { addEventListener() {}, removeEventListener() {}, devicePixelRatio: 1 })
  vi.stubGlobal('cancelAnimationFrame', () => {})
  const hostListeners = new Map<string, Fn>()
  const inside = new Set<unknown>()
  const host = {
    hidden: true, innerHTML: '',
    contains: (t: unknown) => t === host || inside.has(t),
    querySelector: () => null,
    focus: vi.fn(),
    addEventListener: (k: string, f: Fn) => hostListeners.set(k, f),
    removeEventListener: (k: string, f: Fn) => { if (hostListeners.get(k) === f) hostListeners.delete(k) },
  }
  const el = (sel: string | null, isInside: boolean) => {
    const t = { closest: (s: string) => (sel && s.split(',').map(x => x.trim()).includes(sel) ? t : null) }
    if (isInside) inside.add(t)
    return t
  }
  return { docListeners, hostListeners, host: host as typeof host & HTMLElement, el }
}

test('a tap opens the card; ✕, Esc and a tap outside close it', () => {
  const { docListeners, hostListeners, host, el } = fakeDom()
  const card = createCard(host, g, { notes: motum.glossaryNotes })
  card.open(['inversion'], 'contrary motion')
  expect(host.hidden).toBe(false)
  expect(card.openEntry).toBe('inversion')
  expect(host.innerHTML).toContain('In this piece')
  // a tap inside keeps it open
  docListeners.get('click')!({ target: el(null, true) })
  expect(host.hidden).toBe(false)
  // ✕
  hostListeners.get('click')!({ target: el('.close', true) })
  expect(host.hidden).toBe(true)
  expect(card.openEntry).toBeNull()
  // Esc
  card.open(['stretto'])
  expect(host.innerHTML).not.toContain('In this piece')
  docListeners.get('keydown')!({ key: 'Escape' })
  expect(host.hidden).toBe(true)
  // outside: closes, and the roll learns that this tap only closed the card
  card.open(['canon'])
  const tap = { target: el(null, false) }
  docListeners.get('click')!(tap)
  expect(host.hidden).toBe(true)
  expect(card.dismissedBy(tap)).toBe(true)
  expect(card.dismissedBy({ target: null })).toBe(false)
})

test('a tap on another technique word is not an outside tap that swallows it', () => {
  const { docListeners, host, el } = fakeDom()
  const card = createCard(host, g)
  card.open(['canon'])
  const tap = { target: el('.term', false) }
  docListeners.get('click')!(tap)
  expect(card.dismissedBy(tap)).toBe(false)
})

test('"also here" switches the card to the other entry', () => {
  const { hostListeners, host, el } = fakeDom()
  const card = createCard(host, g)
  card.open(['subject', 'inversion'])
  const b = el('.other', true) as { closest: unknown; dataset?: Record<string, string> }
  b.dataset = { entry: 'inversion' }
  hostListeners.get('click')!({ target: b })
  expect(card.openEntry).toBe('inversion')
  expect(host.innerHTML).toContain('data-entry="subject">Subject</button>')
})

test('dispose removes every listener', () => {
  const { docListeners, hostListeners, host } = fakeDom()
  const card = createCard(host, g)
  card.open(['canon'])
  card.dispose()
  expect(docListeners.size).toBe(0)
  expect(hostListeners.size).toBe(0)
  expect(host.hidden).toBe(true)
})

test('closing the card restores the piece to full level (an example may have ducked it)', () => {
  const { host } = fakeDom()
  const sound: boolean[] = []
  const card = createCard(host, g, { onSound: on => sound.push(on) })
  card.open(['inversion'])
  card.close()
  expect(sound).toEqual([false])
})

test('a card opened by "Dux" in a fugue is the Subject card, naming the word', () => {
  expect(cardHtml({ entry: entry('subject'), term: 'Dux', others: [] }))
    .toContain('<h3 id="gcard-title">Subject <span class="term-used">· Dux</span></h3>')
})
