import type { Texture } from '../model'

export const PAPER = '#f1ead9'
export const INK = '#1c1916'
export const SERIF = "'EB Garamond', 'Garamond Libre Accidentals', 'Noto Music Notes', Garamond, Georgia, serif"

/** Tile sizes in CSS px; the patterns scroll with the music by translating by the offset mod tile. */
const HATCH_TILE = 3
const STIPPLE_TILE = 4
const CROSS_TILE = 4

interface Patterns { hatch: CanvasPattern; stipple: CanvasPattern; cross: CanvasPattern }

const cache = new WeakMap<CanvasRenderingContext2D, { dpr: number; p: Patterns }>()

function tile(size: number, dpr: number, draw: (t: CanvasRenderingContext2D, s: number) => void) {
  const px = Math.max(2, Math.round(size * dpr))
  const c = document.createElement('canvas')
  c.width = c.height = px
  const t = c.getContext('2d')!
  draw(t, px)
  return c
}

function makePatterns(ctx: CanvasRenderingContext2D, dpr: number): Patterns {
  // hatch: fine diagonal strokes, lower-left to upper-right, like the mockup's comes
  const hatch = tile(HATCH_TILE, dpr, (t, s) => {
    t.strokeStyle = INK
    t.lineWidth = 0.45 * dpr
    t.beginPath()
    for (const o of [-s, 0, s]) { t.moveTo(o, s); t.lineTo(o + s, 0) }
    t.stroke()
  })
  // stipple: two dots per tile on a diagonal lattice
  const stipple = tile(STIPPLE_TILE, dpr, (t, s) => {
    t.fillStyle = INK
    const r = 0.55 * dpr
    for (const [cx, cy] of [[s * 0.25, s * 0.25], [s * 0.75, s * 0.75]]) {
      t.beginPath(); t.arc(cx, cy, r, 0, Math.PI * 2); t.fill()
    }
  })
  // cross: both diagonals, a wider tile than the hatch so the two read apart
  const cross = tile(CROSS_TILE, dpr, (t, s) => {
    t.strokeStyle = INK
    t.lineWidth = 0.45 * dpr
    t.beginPath()
    for (const o of [-s, 0, s]) { t.moveTo(o, s); t.lineTo(o + s, 0); t.moveTo(o, 0); t.lineTo(o + s, s) }
    t.stroke()
  })
  return {
    hatch: ctx.createPattern(hatch, 'repeat')!, stipple: ctx.createPattern(stipple, 'repeat')!,
    cross: ctx.createPattern(cross, 'repeat')!,
  }
}

/** The hatch, stipple and cross patterns for this context, shifted so they travel with the notes. */
export function patternsFor(ctx: CanvasRenderingContext2D, dpr: number, offsetX: number): Patterns {
  let entry = cache.get(ctx)
  if (!entry || entry.dpr !== dpr) {
    entry = { dpr, p: makePatterns(ctx, dpr) }
    cache.set(ctx, entry)
  }
  const shift = (tileCss: number) => {
    const tilePx = Math.max(2, Math.round(tileCss * dpr)) / dpr
    return ((offsetX % tilePx) + tilePx) % tilePx
  }
  entry.p.hatch.setTransform(new DOMMatrix([1 / dpr, 0, 0, 1 / dpr, shift(HATCH_TILE), 0]))
  entry.p.stipple.setTransform(new DOMMatrix([1 / dpr, 0, 0, 1 / dpr, shift(STIPPLE_TILE), 0]))
  entry.p.cross.setTransform(new DOMMatrix([1 / dpr, 0, 0, 1 / dpr, shift(CROSS_TILE), 0]))
  return entry.p
}

/** One note as an engraved block. `playing` (also used for emphasis) thickens the outline and darkens solid ink. */
export function drawNote(
  ctx: CanvasRenderingContext2D, p: Patterns, texture: Texture,
  x: number, y: number, w: number, h: number, playing: boolean, fade = 1,
) {
  ctx.setLineDash([])
  if (fade < 1) { // a faded note still hides what lies under it: opaque paper first, then the faded drawing
    ctx.globalAlpha = 1
    ctx.fillStyle = PAPER
    ctx.fillRect(x, y, w, h)
  }
  ctx.globalAlpha = fade
  switch (texture) {
    case 'solid':
      ctx.globalAlpha = (playing ? 1 : 0.86) * fade
      ctx.fillStyle = INK
      ctx.fillRect(x, y, w, h)
      ctx.globalAlpha = fade
      if (playing) { ctx.strokeStyle = INK; ctx.lineWidth = 0.8; ctx.strokeRect(x, y, w, h) }
      return
    case 'hatch':
    case 'stipple':
    case 'cross':
      ctx.fillStyle = PAPER
      ctx.fillRect(x, y, w, h)
      ctx.fillStyle = p[texture]
      ctx.fillRect(x, y, w, h)
      ctx.strokeStyle = INK
      ctx.lineWidth = playing ? 1.6 : 0.9
      ctx.strokeRect(x, y, w, h)
      return
    case 'dashed':
      ctx.fillStyle = PAPER
      ctx.fillRect(x, y, w, h)
      ctx.setLineDash([3, 2])
      ctx.strokeStyle = INK
      ctx.lineWidth = playing ? 1.4 : 0.8
      ctx.strokeRect(x, y, w, h)
      ctx.setLineDash([])
      return
    case 'open':
      ctx.fillStyle = PAPER
      ctx.fillRect(x, y, w, h)
      ctx.strokeStyle = INK
      ctx.lineWidth = playing ? 1.6 : 0.9
      ctx.strokeRect(x, y, w, h)
      return
  }
}
