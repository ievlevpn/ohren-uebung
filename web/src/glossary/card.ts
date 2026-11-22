import { buildRoute } from '../router'
import { esc } from '../screens/common'
import { drawFigureBox, figureHtml, stopHear, toggleHear } from './figure-dom'
import type { Glossary, GlossaryEntry } from './model'

export interface CardContent {
  entry: GlossaryEntry
  /** The word that was tapped ("contrary motion"), shown beside the title when it differs. */
  term?: string
  /** The piece's "In this piece" line for this entry (markings glossary_notes). */
  note?: string
  /** Other entries the tapped label names ("subject inverted": Inversion), one tap away. */
  others: GlossaryEntry[]
}

const SEP = '<span class="sep"> · </span>'

/** A definition card, as in the mockup: title, the one-sentence definition, the figure with
 * ▶ hear, "In this piece" when the piece has a note, and the way to the full entry. */
export function cardHtml({ entry: e, term, note, others }: CardContent): string {
  const used = term && term.toLowerCase() !== e.title.toLowerCase() ? ` <span class="term-used">· ${esc(term)}</span>` : ''
  const here = note ? `<div class="where here"><b>In this piece</b>${esc(note)}</div>` : ''
  const also = others.length
    ? `<div class="where also"><b>Also here</b>${others.map(o =>
      `<button type="button" class="other" data-entry="${esc(o.id)}">${esc(o.title)}</button>`).join(SEP)}</div>`
    : ''
  return `<div class="gcard-head"><h3 id="gcard-title">${esc(e.title)}${used}</h3>` +
    `<button type="button" class="close" aria-label="Close">✕</button></div>` +
    `<p class="def">${esc(e.short)}</p>${figureHtml(e)}${here}${also}` +
    `<a class="full" href="${buildRoute({ name: 'index', entry: e.id })}">more in the glossary ☞</a>`
}

export interface Card {
  /** Opens (or replaces) the card on the first of `ids`; the rest are offered as "also here". */
  open(ids: string[], term?: string, opener?: HTMLElement | null): void
  close(): void
  /** The entry shown, or null when closed. */
  readonly openEntry: string | null
  /** True if this tap closed the card (a tap outside it): the roll should not also act on it. */
  dismissedBy(ev: unknown): boolean
  dispose(): void
}

export interface CardOptions {
  /** The piece's "In this piece" lines, by entry id. */
  notes?: Record<string, string>
  /** Runs after the card is filled (the player places it). */
  onShow?: () => void
  /** An example starts (true) or stops (false) sounding; false again when the card closes. */
  onSound?: (on: boolean) => void
}

/**
 * The player's definition card in `host` (hidden while closed). It closes with ✕, Esc or a tap
 * outside it; a tap on another technique word opens that one instead. The music keeps playing
 * (the player ducks it while an example sounds, through `onSound`).
 */
export function createCard(host: HTMLElement, g: Glossary, { notes, onShow, onSound }: CardOptions = {}): Card {
  const byId = new Map(g.entries.map(e => [e.id, e]))
  let ids: string[] = []
  let shown: string | null = null
  let opener: HTMLElement | null = null
  let dismissed: unknown = null

  function render(list: string[], term?: string) {
    const e = byId.get(list[0])
    if (!e) return
    stopHear()
    ids = list
    shown = e.id
    host.innerHTML = cardHtml({
      entry: e, term, note: notes?.[e.id],
      others: list.slice(1).flatMap(id => byId.get(id) ?? []),
    })
    host.hidden = false
    draw() // first: the figure's height is set as it is drawn
    onShow?.()
  }
  function draw() {
    const fig = host.querySelector<HTMLElement>('figure.fig')
    const ex = shown ? byId.get(shown)?.example : undefined
    if (fig && ex) drawFigureBox(fig, ex)
  }
  function close() {
    if (shown === null) return
    stopHear()
    onSound?.(false)
    const was = shown
    shown = null
    host.hidden = true
    host.innerHTML = ''
    const back = opener
    opener = null
    if (back?.isConnected) back.focus()
    // the caption it was opened from has moved on: the same word in the "listen for" line, if there
    else if (back) document.querySelector<HTMLElement>(`.term[data-entry="${CSS.escape(was)}"]`)?.focus()
  }

  const onDocClick = (ev: Event) => {
    if (shown === null) return
    const t = ev.target as Element | null
    if (t && host.contains(t)) return
    if (t?.closest?.('.term')) return // another technique word: it opens its own card
    close()
    dismissed = ev
  }
  const onKey = (ev: KeyboardEvent) => { if (ev.key === 'Escape' && shown !== null) close() }
  const onHostClick = (ev: Event) => {
    const t = ev.target as Element
    if (t.closest('.close')) { close(); return }
    const other = t.closest<HTMLElement>('.other')
    if (other) {
      const id = other.dataset.entry ?? ''
      render([id, ...ids.filter(x => x !== id)])
      host.focus?.()
      return
    }
    const b = t.closest<HTMLButtonElement>('.hear')
    const fig = b?.closest<HTMLElement>('figure')
    const ex = shown ? byId.get(shown)?.example : undefined
    if (b && fig && ex) toggleHear(b, fig, ex, onSound)
  }
  const onResize = () => { if (shown !== null) { draw(); onShow?.() } }
  // capture: an outside tap is seen before the roll or a control acts on it
  document.addEventListener('click', onDocClick, true)
  document.addEventListener('keydown', onKey)
  host.addEventListener('click', onHostClick)
  window.addEventListener('resize', onResize)

  return {
    open(list, term, from) {
      render(list, term)
      opener = from ?? opener
      host.focus?.()
    },
    close,
    get openEntry() { return shown },
    dismissedBy: ev => ev === dismissed,
    dispose() {
      close()
      document.removeEventListener('click', onDocClick, true)
      document.removeEventListener('keydown', onKey)
      host.removeEventListener('click', onHostClick)
      window.removeEventListener('resize', onResize)
    },
  }
}
