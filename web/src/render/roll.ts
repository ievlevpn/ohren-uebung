import type { Note, Piece } from '../model'
import type { Layout } from './layout'
import { fade } from './mute'
import { drawAnnotations, drawEntryOrnaments, drawThreads, drawUnderlays, isEmphasised, type LabelHit } from './techniques'
import { INK, PAPER, SERIF, drawNote, patternsFor } from './textures'

/** playhead: draw the *nunc* line (default true; a glossary figure has none). labels: each label drawn
 * is added there (the player's taps on labels). */
export interface RollOptions { markings: boolean; muted?: ReadonlySet<number>; playhead?: boolean; labels?: LabelHit[] }

const maxDurCache = new WeakMap<Piece, number>()
function maxDuration(piece: Piece): number {
  let m = maxDurCache.get(piece)
  if (m === undefined) {
    m = 0
    for (const n of piece.notes) if (n.d > m) m = n.d
    maxDurCache.set(piece, m)
  }
  return m
}

const unisonCache = new WeakMap<Piece, Map<Note, number>>()
/**
 * Unisons: notes of different voices sounding one pitch at the same time would hide each other (the later one's
 * paper covers the earlier). Each such note gets a vertical offset, a fraction of the note height in [-0.25, 0.25]:
 * spread by voice order (upper voice higher), so part of each stays in view whichever is drawn last. Others are absent.
 */
export function unisonOffsets(piece: Piece): Map<Note, number> {
  let out = unisonCache.get(piece)
  if (out) return out
  out = new Map()
  const byPitch = new Map<number, Note[]>()
  for (const n of piece.notes) {
    let ns = byPitch.get(n.p)
    if (!ns) byPitch.set(n.p, ns = [])
    ns.push(n)
  }
  for (const ns of byPitch.values()) {
    for (const n of ns) {
      const group = ns.filter(m => m === n || (m.v !== n.v && m.s < n.s + n.d - 1e-6 && n.s < m.s + m.d - 1e-6))
      if (group.length < 2) continue
      group.sort((a, b) => a.v - b.v)
      out.set(n, (group.indexOf(n) / (group.length - 1) - 0.5) * 0.5)
    }
  }
  unisonCache.set(piece, out)
  return out
}

/** First index whose start is >= beat (notes are sorted by start). */
function firstFrom(notes: Note[], beat: number): number {
  let lo = 0, hi = notes.length
  while (lo < hi) {
    const mid = (lo + hi) >> 1
    if (notes[mid].s < beat) lo = mid + 1; else hi = mid
  }
  return lo
}

/** Faint hairlines at every C, like the ruling of an engraver's plate. */
function drawStaff(ctx: CanvasRenderingContext2D, L: Layout) {
  ctx.save()
  ctx.strokeStyle = INK
  ctx.globalAlpha = 0.18
  ctx.lineWidth = 0.5
  for (let p = Math.ceil(L.lo / 12) * 12; p <= L.hi; p += 12) {
    const y = Math.round(L.y(p) * L.dpr) / L.dpr
    ctx.beginPath(); ctx.moveTo(0, y); ctx.lineTo(L.width, y); ctx.stroke()
  }
  ctx.restore()
}

const snapTo = (L: Layout, v: number) => Math.round(v * L.dpr) / L.dpr

/** The rectangle a note is drawn in (CSS pixels). */
function noteRect(L: Layout, n: Note, now: number, unison: Map<Note, number>) {
  const span = n.d * L.beatWidth
  const gap = Math.min(2, span * 0.15)
  const h = L.noteHeight
  return {
    x: snapTo(L, L.x(n.s, now)), w: Math.max(1.5, snapTo(L, span - gap)),
    y: snapTo(L, L.y(n.p) - h / 2 + (unison.get(n) ?? 0) * h), h,
  }
}

/** Touch slop: how far (CSS px) from a note's rectangle a tap still counts as on it. */
export const TOUCH_SLOP = 8

/**
 * The voice of the note drawn at (x, y): the topmost (drawn last) note under the point, else the nearest note
 * within `slop` px of it (topmost on ties); null on empty paper.
 */
export function voiceAt(piece: Piece, L: Layout, now: number, x: number, y: number, slop = TOUCH_SLOP): number | null {
  const unison = unisonOffsets(piece)
  const b0 = now - L.playheadX / L.beatWidth - maxDuration(piece)
  const b1 = now + (L.width - L.playheadX) / L.beatWidth
  let best: number | null = null, bestD = slop + 1e-9
  for (let i = piece.notes.length - 1; i >= 0; i--) {
    const n = piece.notes[i]
    if (n.s > b1 || n.s + n.d < b0) continue
    const r = noteRect(L, n, now, unison)
    const d = Math.hypot(Math.max(r.x - x, 0, x - (r.x + r.w)), Math.max(r.y - y, 0, y - (r.y + r.h)))
    if (d === 0) return n.v
    if (d < bestD) { bestD = d; best = n.v }
  }
  return best
}

function drawNotes(ctx: CanvasRenderingContext2D, piece: Piece, L: Layout, now: number, markings: boolean, muted?: ReadonlySet<number>) {
  const pats = patternsFor(ctx, L.dpr, L.x(0, now))
  const b0 = now - L.playheadX / L.beatWidth
  const b1 = now + (L.width - L.playheadX) / L.beatWidth
  const unison = unisonOffsets(piece)
  ctx.save()
  for (let i = firstFrom(piece.notes, b0 - maxDuration(piece)); i < piece.notes.length; i++) {
    const n = piece.notes[i]
    if (n.s > b1) break
    if (n.s + n.d < b0) continue
    const { x, y, w, h } = noteRect(L, n, now, unison)
    const heavy = (n.s <= now && now < n.s + n.d) || (markings && isEmphasised(piece, n, now))
    drawNote(ctx, pats, piece.voices[n.v]?.texture ?? 'open', x, y, w, h, heavy, fade(muted, n.v))
  }
  ctx.restore()
}

function drawPlayhead(ctx: CanvasRenderingContext2D, L: Layout) {
  const x = Math.round(L.playheadX * L.dpr) / L.dpr
  ctx.save()
  ctx.strokeStyle = INK
  ctx.lineWidth = 0.9
  ctx.setLineDash([])
  ctx.beginPath(); ctx.moveTo(x, 4); ctx.lineTo(x, L.bottom + 2); ctx.stroke()
  ctx.fillStyle = INK
  ctx.font = `italic 13px ${SERIF}`
  ctx.textAlign = 'center'
  ctx.textBaseline = 'alphabetic'
  ctx.fillText('nunc', x, Math.min(L.height - 5, L.bottom + 17))
  ctx.restore()
}

/**
 * Draws one frame of the engraved roll at beat `now`. The canvas is expected to be
 * `layout.width × layout.dpr` device pixels wide (and likewise high); this sets the transform.
 */
export function drawRoll(
  ctx: CanvasRenderingContext2D, piece: Piece, layout: Layout, now: number, options: RollOptions,
) {
  const L = layout
  ctx.setTransform(L.dpr, 0, 0, L.dpr, 0, 0)
  ctx.globalAlpha = 1
  ctx.fillStyle = PAPER
  ctx.fillRect(0, 0, L.width, L.height)
  drawStaff(ctx, L)
  if (options.markings) {
    drawUnderlays(ctx, piece, L, now)
    drawThreads(ctx, piece, L, now, options.muted)
  }
  drawNotes(ctx, piece, L, now, options.markings, options.muted)
  if (options.markings) {
    drawEntryOrnaments(ctx, piece, L, now, options.muted)
    drawAnnotations(ctx, piece, L, now, options.muted, options.labels)
  }
  if (options.playhead !== false) drawPlayhead(ctx, L)
}
