import { canvasDpr } from '../render/layout'
import { esc } from '../screens/common'
import { drawFigure, figureHeight, figureLayout, figureNow } from './figure'
import { examplePosition, playExample, stopExample } from './hear'
import type { Example, GlossaryEntry } from './model'

/** An entry's framed figure: the drawing, its caption and ▶ hear (none if the entry has no example). */
export function figureHtml(e: GlossaryEntry): string {
  if (!e.example) return ''
  const cap = esc(e.example.caption)
  return `<figure class="fig" data-entry="${esc(e.id)}">` +
    `<div class="figroll"><canvas role="img" aria-label="${cap}"></canvas><i class="cursor" aria-hidden="true"></i></div>` +
    `<figcaption><span>${cap}</span><button type="button" class="hear" data-entry="${esc(e.id)}">▶ hear</button></figcaption></figure>`
}

/** Draws the example into a figure at its box's width. */
export function drawFigureBox(fig: HTMLElement, ex: Example): void {
  const box = fig.querySelector<HTMLElement>('.figroll')
  const canvas = box?.querySelector('canvas')
  const w = box?.clientWidth ?? 0
  if (!box || !canvas || w < 10) return
  const h = figureHeight(ex, w), dpr = canvasDpr(window.devicePixelRatio)
  box.style.height = `${h}px`
  canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr)
  canvas.style.width = `${w}px`; canvas.style.height = `${h}px`
  drawFigure(canvas.getContext('2d')!, ex, figureLayout(ex, w, h, dpr))
}

let raf = 0

/** A hairline that walks across the sounding figure (no text moves). */
function follow(fig: HTMLElement, ex: Example, cursor: HTMLElement) {
  const beat = examplePosition(ex)
  if (beat === null) { cursor.style.display = 'none'; return }
  const box = fig.querySelector<HTMLElement>('.figroll')!
  const L = figureLayout(ex, box.clientWidth, box.clientHeight, 1)
  cursor.style.display = beat >= 0 ? 'block' : 'none'
  cursor.style.left = `${L.x(beat, figureNow(ex))}px`
  raf = requestAnimationFrame(() => follow(fig, ex, cursor))
}

/** ▶ hear pressed: plays the figure's example (stopping any other), or stops it if it is the one sounding.
 * `onSound` hears when it starts sounding (true) and when it ends or is stopped (false). */
export function toggleHear(b: HTMLButtonElement, fig: HTMLElement, ex: Example, onSound?: (on: boolean) => void): void {
  if (b.classList.contains('on')) { stopExample(); return }
  b.textContent = 'loading…'
  b.classList.add('on')
  const cursor = fig.querySelector<HTMLElement>('.cursor')!
  playExample(ex, () => {
    b.classList.remove('on'); b.textContent = '▶ hear'
    cancelAnimationFrame(raf); cursor.style.display = 'none'
    onSound?.(false)
  }).then(() => {
    if (!b.classList.contains('on')) return
    b.textContent = '■ stop'
    onSound?.(true)
    cancelAnimationFrame(raf)
    follow(fig, ex, cursor)
  }, (e) => {
    console.error(e)
    b.classList.remove('on'); b.textContent = '▶ hear (could not load)'
  })
}

/** Stops the sounding example and its cursor. */
export function stopHear(): void {
  stopExample()
  cancelAnimationFrame(raf)
}
