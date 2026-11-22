import { keepOffline } from '../offline'
import type { Collection, Library } from '../model'
import { loadRecent } from '../recent'
import { buildRoute } from '../router'
import { search } from '../search'
import { collectionHref, collectionOf, esc, fleuron, leaderRow, pieceHref, summary } from './common'
import type { Glossary } from '../glossary/model'
import { mountIndex, renderIndex } from './index'

export type ShelfTab = 'collections' | 'index' | 'recent'

const TABS: [ShelfTab, string, string][] = [
  ['collections', 'Collections', buildRoute({ name: 'shelf' })],
  ['index', 'Glossary', buildRoute({ name: 'index' })],
  ['recent', 'Recently heard', buildRoute({ name: 'recent' })],
]

function plural(n: number, word: string): string { return `${n} ${word}${n === 1 ? '' : 's'}` }

/** "3 canons · 1 fugue" from the pieces' techniques. */
export function contentsCount(lib: Library, c: Collection): string {
  const ids = c.books.flatMap(b => b.pieces)
  let fugues = 0, canons = 0
  for (const id of ids) {
    if (summary(lib, id)?.techniques.includes('fugue')) fugues++; else canons++
  }
  const parts = []
  if (canons) parts.push(plural(canons, 'canon'))
  if (fugues) parts.push(plural(fugues, 'fugue'))
  if (c.books.length > 1) parts.push(plural(c.books.length, 'book'))
  return parts.join(' · ')
}

function plates(lib: Library): string {
  return `<nav class="shelf" aria-label="Collections">${lib.collections.map(c => `
    <a class="plate" href="${collectionHref(c.id)}">
      <span class="plate-k">${esc([c.numeral, c.catalogue].filter(Boolean).join(' · '))}</span>
      <span class="plate-n">${esc(c.name)}</span>
      <span class="plate-c">${esc(contentsCount(lib, c))}</span>
    </a>`).join('')}</nav>`
}

function recent(lib: Library): string {
  const rows = loadRecent().flatMap(id => {
    const p = summary(lib, id)
    return p ? [leaderRow(pieceHref(p.id), p.title, collectionOf(lib, p)?.name ?? '')] : []
  })
  return rows.length ? `<div class="list">${rows.join('')}</div>`
    : `<p class="empty">Nothing heard yet. Open a piece from the shelf.</p>`
}

function results(lib: Library, q: string): string {
  const found = search(lib, q)
  if (!found.length) return `<p class="empty">Nothing found for “${esc(q.trim())}”.</p>`
  return `<div class="list">${found.map(p =>
    leaderRow(pieceHref(p.id), p.title, `${collectionOf(lib, p)?.name ?? ''} · ${p.catalogue} · ${p.key}`)).join('')}</div>`
}

/** The shelf page and its two sister tabs (the glossary, recently heard), with the search line. The glossary
 * tab needs `glossary` and may open at an `entry`. Returns a function that stops the glossary's sound. */
export function renderShelf(app: HTMLElement, lib: Library, tab: ShelfTab,
  glossary?: Glossary, entry?: string): () => void {
  app.innerHTML = `<main class="sheet">
    <header class="top">
      <div class="brand"><small>Canones et Fugae</small><span>Ohren-Übung</span><em class="subtitle">bestehend in Fugen und Canons von Joh. Seb. Bach, denen Liebhabern zur Gemüths-Ergötzung sichtbar gemacht</em></div>
      <nav class="tabs">${TABS.map(([t, label, href]) =>
        `<a href="${href}"${t === tab ? ' class="on" aria-current="page"' : ''}>${label}</a>`).join('')}</nav>
      <input class="search" type="search" placeholder="Seek a piece, BWV, key…" aria-label="Search" autocomplete="off" spellcheck="false">
    </header>
    ${fleuron}
    <section class="content"></section>
    <p class="credits"><a href="credits.txt">Sources &amp; credits</a>${'serviceWorker' in navigator ? ' · <button type="button" class="offline-btn">keep everything for offline use (≈ 6 MB)</button>' : ''}</p>
  </main>`
  const content = app.querySelector<HTMLElement>('.content')!
  app.querySelector<HTMLButtonElement>('.offline-btn')?.addEventListener('click', async (e) => {
    const btn = e.currentTarget as HTMLButtonElement
    btn.disabled = true
    const failed = await keepOffline(lib, (d, n) => { btn.textContent = `keeping for offline use… ${Math.round((100 * d) / n)} %` })
    btn.textContent = failed ? `kept, except ${failed} files — try again online` : 'everything is kept for offline use'
    btn.disabled = failed === 0
  })
  const input = app.querySelector<HTMLInputElement>('.search')!
  let unmount = () => {}
  const show = (at?: string) => {
    unmount(); unmount = () => {}
    const q = input.value
    if (q.trim()) content.innerHTML = results(lib, q)
    else if (tab === 'collections') content.innerHTML = plates(lib)
    else if (tab === 'index' && glossary) {
      content.innerHTML = renderIndex(lib, glossary)
      unmount = mountIndex(content, glossary, at)
    } else if (tab === 'index') content.innerHTML = `<p class="empty">The glossary could not be loaded.</p>`
    else content.innerHTML = recent(lib)
  }
  input.addEventListener('input', () => show())
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') {
      const first = search(lib, input.value)[0]
      if (first) location.hash = pieceHref(first.id)
    }
  })
  show(entry)
  return () => unmount()
}
