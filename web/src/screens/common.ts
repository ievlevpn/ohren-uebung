import type { Collection, Library, PieceSummary } from '../model'
import { buildRoute } from '../router'

export function esc(s: string): string {
  return s.replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]!)
}

export const pieceHref = (id: string) => buildRoute({ name: 'piece', id })
export const collectionHref = (id: string) => buildRoute({ name: 'collection', id })

export function collectionOf(lib: Library, piece: { collection: string }): Collection | undefined {
  return lib.collections.find(c => c.id === piece.collection)
}

export function summary(lib: Library, id: string): PieceSummary | undefined {
  return lib.pieces.find(p => p.id === id)
}

/** "II · 2 of 4": collection numeral and place in the collection; where a collection has
 *  several books, the place in the book: "VI · Sinfonias · 15 of 15". */
export function positionLabel(lib: Library, pieceId: string): string {
  for (const c of lib.collections) {
    for (const b of c.books) {
      const i = b.pieces.indexOf(pieceId)
      if (i < 0) continue
      const p = summary(lib, pieceId)
      if (p?.number !== undefined) { // its own number: "V · Book I · Fugue 4"
        const kind = p.title.split(' ')[0]
        return [c.numeral, b.name, `${kind} ${p.number}`].filter(Boolean).join(' · ')
      }
      if (c.books.length > 1 && b.name) return `${c.numeral} · ${b.name} · ${i + 1} of ${b.pieces.length}`
      const ids = c.books.flatMap(x => x.pieces)
      return `${c.numeral} · ${ids.indexOf(pieceId) + 1} of ${ids.length}`
    }
  }
  return ''
}

/** A dotted-leader row: title … italic note. */
export function leaderRow(href: string, title: string, note: string, extra = ''): string {
  return `<a class="row" href="${href}"${extra}><span class="row-title">${esc(title)}</span>` +
    `<span class="dots" aria-hidden="true"></span><i class="row-note">${esc(note)}</i></a>`
}

export const fleuron = `<div class="rule" aria-hidden="true"><span></span>❦<span></span></div>`

/** The pieces before and after `pieceId` in its collection (across its books), in the collection's order. */
export function neighbours(lib: Library, pieceId: string): { prev?: string; next?: string } {
  for (const c of lib.collections) {
    const ids = c.books.flatMap(b => b.pieces)
    const i = ids.indexOf(pieceId)
    if (i >= 0) return { prev: ids[i - 1], next: ids[i + 1] }
  }
  return {}
}
