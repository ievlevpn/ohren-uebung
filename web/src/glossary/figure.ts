import { layoutFor, type Layout } from '../render/layout'
import { drawRoll } from '../render/roll'
import type { Piece } from '../model'
import { exampleEnd } from './model'

/** Paper left and right of the music in a figure (CSS px). */
const SIDE = 10
/** Below this width a figure is laid out for a phone. */
const NARROW = 480

/** Height (CSS px) for a figure of this width: the annotation band plus a row per semitone. */
export function figureHeight(ex: Piece, width: number): number {
  const ps = ex.notes.map(n => n.p)
  const rows = Math.max(...ps) - Math.min(...ps) + 5
  const row = width < NARROW ? 6.5 : 8
  const band = layoutFor(ex, width, 400, 1, 0).band.height
  return Math.round(Math.min(320, Math.max(100, band + rows * row + 6)))
}

/** The beat a figure is drawn at: after the music and its emphasis, so every thread and mark shows and nothing sounds. */
export function figureNow(ex: Piece): number {
  return exampleEnd(ex) + 2
}

/** The roll's layout, stretched so the whole example fits the width, frozen at `figureNow`. */
export function figureLayout(ex: Piece, width: number, height: number, dpr: number): Layout {
  const L = layoutFor(ex, width, height, dpr, 4)
  const beatWidth = (width - 2 * SIDE) / exampleEnd(ex)
  const playheadX = SIDE + figureNow(ex) * beatWidth
  return { ...L, beatWidth, playheadX, x: (beat, now) => playheadX + (beat - now) * beatWidth }
}

/** Draws an example as the roll would show it once played, without the playhead. */
export function drawFigure(ctx: CanvasRenderingContext2D, ex: Piece, L: Layout): void {
  drawRoll(ctx, ex, L, figureNow(ex), { markings: true, playhead: false })
}
