import type { Library } from '../model'
import { buildRoute } from '../router'
import { esc, leaderRow, pieceHref, summary } from './common'

/** A collection's contents: books, dotted leaders, an italic "listen for" note per piece (from library.json). */
export function renderCollection(app: HTMLElement, lib: Library, id: string): void {
  const c = lib.collections.find(x => x.id === id)
  if (!c) { location.hash = buildRoute({ name: 'shelf' }); return }
  const ids = c.books.flatMap(b => b.pieces)
  const books = c.books.map(b => {
    const head = b.name ? `<h2 class="bookhead">${esc(b.name)}</h2>` : ''
    const rows = b.pieces.map((pid, i) => {
      const p = summary(lib, pid)
      const n = p?.number ?? i + 1 // its own number (WTC fugue 3), else each book counts from 1
      return p ? leaderRow(pieceHref(pid), `${n} · ${p.title}`, p.listenFor || p.techniques.join(', ')) : ''
    }).join('')
    return head + rows
  }).join('')
  const wide = ids.length > 6 ? ' cols' : ''
  app.innerHTML = `<main class="sheet"><div class="content">
    <nav class="crumb"><a href="${buildRoute({ name: 'shelf' })}">☜ Shelf</a><span> · ${esc([c.numeral, c.catalogue].filter(Boolean).join(' · '))}</span></nav>
    <h1 class="brand-title">${esc(c.name)}</h1>
    <p class="cnote">${esc(c.note)}</p>
    <div class="rule" aria-hidden="true"><span></span>❦<span></span></div>
    <section class="list${wide}">${books}</section>
  </div></main>`
}
