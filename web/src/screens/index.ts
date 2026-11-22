import { drawFigureBox, figureHtml, stopHear, toggleHear } from '../glossary/figure-dom'
import type { Glossary, GlossaryEntry } from '../glossary/model'
import type { Library } from '../model'
import { buildRoute } from '../router'
import { collectionOf, esc, pieceHref, summary } from './common'

/** "Hear it in" shows this many pieces, then "and N more". */
const SHOWN = 6

export const entryHref = (id: string) => buildRoute({ name: 'index', entry: id })

function hearItIn(lib: Library, e: GlossaryEntry): string {
  const refs = e.pieces.flatMap(({ id, note }) => {
    const p = summary(lib, id)
    if (!p) return []
    const where = `${collectionOf(lib, p)?.name ?? ''}, ${p.catalogue}`
    return [`<a href="${pieceHref(id)}" title="${esc(where)}">${esc(p.title)}</a>${note ? ` <i>${esc(note)}</i>` : ''}`]
  })
  if (!refs.length) return ''
  const sep = '<span class="sep"> · </span>'
  const head = refs.slice(0, SHOWN).join(sep)
  const rest = refs.slice(SHOWN)
  const more = rest.length
    ? `<span class="sep"> · </span><button type="button" class="more" aria-expanded="false">and ${rest.length} more</button>` +
      `<span class="rest" hidden>${rest.join(sep)}</span>`
    : ''
  return `<div class="where"><b>Hear it in</b>${head}${more}</div>`
}

function seeAlso(g: Glossary, e: GlossaryEntry): string {
  const refs = e.related.flatMap(id => {
    const r = g.entries.find(x => x.id === id)
    return r ? [`<a href="${entryHref(r.id)}">${esc(r.title)}</a>`] : []
  })
  return refs.length ? `<div class="where"><b>See also</b>${refs.join('<span class="sep"> · </span>')}</div>` : ''
}

/** The glossary of techniques, alphabetical with letter heads, like the back of a book: each entry
 * defined, illustrated with a figure drawn by the roll's engine, and linked to the pieces that use it. */
export function renderIndex(lib: Library, g: Glossary): string {
  let letter = ''
  const out: string[] = ['<div class="gloss">']
  for (const e of g.entries) {
    const L = e.title.charAt(0).toUpperCase()
    if (L !== letter) { letter = L; out.push(`<div class="letter">${esc(L)}</div>`) }
    const also = e.also ? ` <small>${esc(e.also)}</small>` : ''
    out.push(`<article class="entry" id="g-${esc(e.id)}"><h2>${esc(e.title)}${also}</h2>` +
      `<p>${esc(e.text)}</p>${figureHtml(e)}${hearItIn(lib, e)}${seeAlso(g, e)}</article>`)
  }
  out.push('</div>')
  return out.join('')
}

/**
 * Brings the rendered glossary to life: draws each figure at its box's width (again on resize) and wires
 * ▶ hear. `entry` scrolls that entry into view. Returns a function that stops sound and observers.
 */
export function mountIndex(root: HTMLElement, g: Glossary, entry?: string): () => void {
  const byId = new Map(g.entries.map(e => [e.id, e]))
  const exampleOf = (fig: HTMLElement) => byId.get(fig.dataset.entry ?? '')?.example
  const draw = (fig: HTMLElement) => {
    const ex = exampleOf(fig)
    if (ex) drawFigureBox(fig, ex)
  }
  const figures = [...root.querySelectorAll<HTMLElement>('figure.fig')]
  const widths = new WeakMap<Element, number>()
  const ro = new ResizeObserver(changes => {
    for (const c of changes) {
      const w = Math.round(c.contentRect.width)
      if (widths.get(c.target) === w) continue // our own height change
      widths.set(c.target, w)
      draw(c.target.closest<HTMLElement>('figure')!)
    }
  })
  for (const f of figures) ro.observe(f.querySelector('.figroll')!)
  figures.forEach(draw) // at once, so the page has its height before scrolling to an entry
  // the first entry under a letter scrolls to its letter head, so the letter stays in view
  const article = entry ? root.querySelector(`#g-${CSS.escape(entry)}`) : null
  const prev = article?.previousElementSibling
  const target = prev?.classList.contains('letter') ? prev : article
  target?.scrollIntoView({ block: 'start' })
  const scrolled = window.scrollY
  // the face changes line heights: draw again with it, and come back to the entry
  const faces = ["17px 'EB Garamond'", "italic 17px 'EB Garamond'", "12px 'EB Garamond'"].map(f => document.fonts.load(f))
  Promise.all(faces).then(() => document.fonts.ready).then(() => {
    figures.forEach(draw)
    // only if the reader has not scrolled meanwhile
    if (target && window.scrollY === scrolled) requestAnimationFrame(() => target.scrollIntoView({ block: 'start' }))
  }, () => {})

  const onClick = (ev: Event) => {
    const more = (ev.target as Element).closest<HTMLButtonElement>('button.more')
    if (more) { // the rest of the list opens in place, after the separator already there
      const rest = more.nextElementSibling as HTMLElement | null
      more.remove()
      if (rest) { rest.hidden = false; rest.querySelector('a')?.focus() }
      return
    }
    const b = (ev.target as Element).closest<HTMLButtonElement>('button.hear')
    if (!b) return
    const fig = b.closest<HTMLElement>('figure')!
    const ex = exampleOf(fig)
    if (ex) toggleHear(b, fig, ex)
  }
  root.addEventListener('click', onClick)
  return () => {
    stopHear()
    ro.disconnect()
    root.removeEventListener('click', onClick)
  }
}
