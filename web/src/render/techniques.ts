import type { Mark, Note, Piece, Thread } from '../model'
import { barOf } from '../model'
import type { Layout } from './layout'
import { markFade, threadFade } from './mute'
import { INK, PAPER, SERIF } from './textures'

/** Threads fade in over this many beats once their follower note starts. */
const THREAD_FADE = 0.35
/** Broken threads (the follower departs from the rule) are drawn at this opacity. */
export const BROKEN_ALPHA = 0.15
const LABEL_FONT = `italic 10.5px ${SERIF}`

interface StretchSegment { start: number; solid: number; full: number; label: string; mark: Mark }
interface Derived {
  /** Threads sorted by the start of their follower note. */
  threads: Thread[]
  /** When the first follower note starts (the technique becomes audible). */
  followerStart: number
  firstEntry: Mark | null
  /** The first entry of each subject (a fugue on several subjects has one per subject). */
  openings: Set<Mark>
  entryNotes: Map<Mark, Note[]>
  /** Every note that belongs to a fugue entry, with the end beat of its entry. */
  entryOf: Map<Note, number>
  riseBands: Map<Mark, { lo: number; hi: number }>
  stretch: StretchSegment[]
}

const derivedCache = new WeakMap<Piece, Derived>()

/** The subject an entry label names in a fugue on several subjects ("answer II" → "II",
 * "subject III inverted" → "III"; prep/fugue_prep/build.py); null for a one-subject label. */
export function subjectOf(label: string | null | undefined): string | null {
  const m = /^(?:subject|answer)\s+(I{1,3}|IV)\b/.exec(label ?? '')
  return m ? m[1] : null
}

/** Each subject's first entry, where its links lead: the first entry of the piece and, in a
 * double or triple fugue, the first entry of every later subject. `entries` sorted by start. */
export function subjectOpenings(entries: readonly Mark[]): Set<Mark> {
  const out = new Set<Mark>()
  const seen = new Set<string>()
  if (entries.length) out.add(entries[0])
  for (const e of entries) {
    const s = subjectOf(e.label)
    if (s === null || seen.has(s)) continue
    seen.add(s)
    out.add(e)
  }
  return out
}

function quantile(sorted: number[], q: number): number {
  if (sorted.length === 0) return 60
  return sorted[Math.min(sorted.length - 1, Math.max(0, Math.round(q * (sorted.length - 1))))]
}

/** Follower segments of an augmentation/diminution: one per leader bar. */
function stretchSegments(piece: Piece, m: Mark): StretchSegment[] {
  const groups = new Map<number, { a0: number; a1: number; b0: number; b1: number }>()
  for (const t of piece.threads) {
    const a = piece.notes[t.a], b = piece.notes[t.b]
    if (m.voice != null && b.v !== m.voice) continue
    if (b.s < m.start || b.s > m.end) continue
    const bar = barOf(piece, a.s)
    const g = groups.get(bar)
    if (!g) groups.set(bar, { a0: a.s, a1: a.s + a.d, b0: b.s, b1: b.s + b.d })
    else {
      g.a0 = Math.min(g.a0, a.s); g.a1 = Math.max(g.a1, a.s + a.d)
      g.b0 = Math.min(g.b0, b.s); g.b1 = Math.max(g.b1, b.s + b.d)
    }
  }
  const out: StretchSegment[] = []
  for (const g of groups.values()) {
    const lead = g.a1 - g.a0, follow = g.b1 - g.b0
    out.push({ start: g.b0, solid: Math.min(lead, follow), full: Math.max(lead, follow), label: m.label ?? '', mark: m })
  }
  return out.sort((a, b) => a.start - b.start)
}

export function derive(piece: Piece): Derived {
  const hit = derivedCache.get(piece)
  if (hit) return hit
  const threads = [...piece.threads].sort((x, y) => piece.notes[x.b].s - piece.notes[y.b].s)
  const followerStart = threads.length ? piece.notes[threads[0].b].s : Infinity
  const entries = piece.marks.filter(m => m.kind === 'entry').sort((a, b) => a.start - b.start)
  const entryNotes = new Map<Mark, Note[]>()
  for (const e of entries) {
    entryNotes.set(e, piece.notes.filter(n => !n.c && n.v === e.voice && n.s >= e.start - 1e-6 && n.s < e.end - 1e-6))
  }
  const entryOf = new Map<Note, number>()
  for (const [e, ns] of entryNotes) for (const n of ns) entryOf.set(n, Math.max(entryOf.get(n) ?? -Infinity, e.end))
  const riseBands = new Map<Mark, { lo: number; hi: number }>()
  for (const m of piece.marks) {
    if (m.kind !== 'rise') continue
    const ps = piece.notes.filter(n => n.s >= m.start && n.s < m.end).map(n => n.p).sort((a, b) => a - b)
    riseBands.set(m, { lo: quantile(ps, 0.15), hi: quantile(ps, 0.85) })
  }
  const stretch = piece.marks.filter(m => m.kind === 'stretch').flatMap(m => stretchSegments(piece, m))
  const d = { threads, followerStart, firstEntry: entries[0] ?? null, openings: subjectOpenings(entries), entryNotes, entryOf, riseBands, stretch }
  derivedCache.set(piece, d)
  return d
}

const clamp01 = (v: number) => Math.min(1, Math.max(0, v))
const visible = (L: Layout, x0: number, x1: number) => Math.max(x0, x1) >= -20 && Math.min(x0, x1) <= L.width + 20

/** A label as drawn (CSS px box around the lettering) and the mark it belongs to: a tap on it opens a card. */
export interface LabelHit { x: number; y: number; w: number; h: number; text: string; mark: Mark | null }
/** Where a drawn label is recorded (absent: nowhere). */
interface Sink { hits?: LabelHit[]; mark: Mark | null }

/** A tap target is at least this tall (and the lettering's width plus a little). */
const TARGET = 44

/** The label whose tap target holds (x, y): the nearest to its centre when targets overlap; null if none. */
export function labelAt(hits: readonly LabelHit[], x: number, y: number): LabelHit | null {
  let best: LabelHit | null = null, bestD = Infinity
  for (const h of hits) {
    const cx = h.x + h.w / 2, cy = h.y + h.h / 2
    const halfW = Math.max(TARGET, h.w + 8) / 2, halfH = Math.max(TARGET, h.h) / 2
    if (Math.abs(x - cx) > halfW || Math.abs(y - cy) > halfH) continue
    const d = Math.hypot(x - cx, y - cy)
    if (d < bestD) { bestD = d; best = h }
  }
  return best
}

/** Text is never faded: every label is drawn at full ink, whatever alpha the caller left set. */
function label(ctx: CanvasRenderingContext2D, text: string, x: number, y: number, align: CanvasTextAlign = 'left', sink?: Sink) {
  ctx.save()
  ctx.globalAlpha = 1
  ctx.font = LABEL_FONT
  ctx.textAlign = align
  ctx.textBaseline = 'alphabetic'
  // clear the paper behind the lettering, as an engraver does: a box down to just above
  // the baseline's bracket, and a halo around descenders below it
  ctx.save()
  ctx.setLineDash([])
  ctx.globalAlpha = 1
  const w = ctx.measureText(text).width
  const left = align === 'center' ? x - w / 2 : align === 'right' ? x - w : x
  ctx.fillStyle = PAPER
  ctx.fillRect(left - 2, y - 9, w + 4, 10.5)
  sink?.hits?.push({ x: left, y: y - 9, w, h: 10.5, text, mark: sink.mark })
  ctx.strokeStyle = PAPER
  ctx.lineWidth = 3
  ctx.lineJoin = 'round'
  ctx.strokeText(text, x, y)
  ctx.restore()
  ctx.fillStyle = INK
  ctx.fillText(text, x, y)
  ctx.restore()
}

/** A label at the left of a span, kept on screen while the span is, and dropped once it no longer fits. */
function fitLabel(ctx: CanvasRenderingContext2D, text: string, x0: number, x1: number, y: number, sink?: Sink) {
  ctx.font = LABEL_FONT
  const at = Math.max(x0, 0) + 4
  if (at + ctx.measureText(text).width > x1 - 2) return
  label(ctx, text, at, y, 'left', sink)
}

/** y of a mirror axis: between the axis pitch and the row above, where mirrored pairs meet. */
export function mirrorAxisY(L: Pick<Layout, 'y'>, pitch: number): number {
  return L.y(pitch + 0.5)
}

/** The pointer printed at the left edge when the opening subject (or motive) has scrolled
 * off screen; bars count from the end of the upbeat, if the piece has one. */
export function railPointer(first: Mark, beatsPerBar: number, xFirst: number, pickup = 0): string | null {
  if (xFirst >= 0) return null
  const bar = barOf({ beatsPerBar, pickup }, first.start)
  return `\u261c ${first.label ?? 'subject'}, ${bar < 1 ? 'upbeat' : `bar ${bar}`}`
}

function hline(ctx: CanvasRenderingContext2D, x0: number, x1: number, y: number) {
  ctx.beginPath(); ctx.moveTo(x0, y); ctx.lineTo(x1, y); ctx.stroke()
}

/** A square engraved bracket: a hairline with short ticks turned down at both ends. */
function bracket(ctx: CanvasRenderingContext2D, x0: number, x1: number, y: number, tick = 3) {
  ctx.beginPath()
  ctx.moveTo(x0, y + tick); ctx.lineTo(x0, y); ctx.lineTo(x1, y); ctx.lineTo(x1, y + tick)
  ctx.stroke()
}

/** Behind the notes: per-tonos rise bands, mirror axes, the crab's vertical axis. */
export function drawUnderlays(ctx: CanvasRenderingContext2D, piece: Piece, L: Layout, now: number) {
  const D = derive(piece)
  ctx.save()
  ctx.strokeStyle = INK
  ctx.fillStyle = INK
  // per tonos: each rise is a faint band over the middle of the texture, a step higher each time
  let prev: { x: number; top: number } | null = null
  for (const m of piece.marks) {
    if (m.kind !== 'rise') continue
    const b = D.riseBands.get(m)!
    const x0 = L.x(m.start, now), x1 = L.x(m.end, now)
    const top = L.y(b.hi) - L.rowHeight / 2, bot = L.y(b.lo) + L.rowHeight / 2
    if (visible(L, x0, x1)) {
      ctx.globalAlpha = 0.045
      ctx.fillRect(x0, top, x1 - x0, bot - top)
      ctx.globalAlpha = 0.45
      ctx.lineWidth = 0.6
      ctx.setLineDash([])
      hline(ctx, x0, x1, top)
      ctx.setLineDash([2, 3])
      hline(ctx, x0, x1, bot)
    }
    if (prev && visible(L, x0 - 1, x0 + 1)) {
      // the step up from the last key to this one
      ctx.setLineDash([])
      ctx.globalAlpha = 0.6
      ctx.lineWidth = 0.8
      ctx.beginPath(); ctx.moveTo(x0, prev.top); ctx.lineTo(x0, top); ctx.stroke()
    }
    prev = { x: x0, top }
  }
  // inversion: a dashed horizontal mirror, faint until the follower has entered
  for (const m of piece.marks) {
    if (m.kind !== 'mirror-axis' || m.pitch == null) continue
    const x0 = Math.max(-2, L.x(m.start, now)), x1 = Math.min(L.width + 2, L.x(m.end, now))
    if (x1 <= x0) continue
    ctx.globalAlpha = 0.15 + 0.75 * clamp01(now - D.followerStart + 1)
    ctx.lineWidth = 0.8
    ctx.setLineDash([5, 3])
    hline(ctx, x0, x1, mirrorAxisY(L, m.pitch))
    ctx.setLineDash([])
  }
  // crab: the piece turns around a vertical mirror at its midpoint in time
  for (const m of piece.marks) {
    if (m.kind !== 'crab-axis') continue
    const x = L.x(m.start, now)
    if (!visible(L, x, x)) continue
    ctx.globalAlpha = 0.9
    ctx.lineWidth = 0.8
    ctx.setLineDash([5, 3])
    ctx.beginPath(); ctx.moveTo(x, L.band.labelY + 4); ctx.lineTo(x, L.bottom); ctx.stroke()
    ctx.setLineDash([])
  }
  ctx.restore()
}

/**
 * The engraved accidental tick of an adjusted thread (Bach answers a semitone off the rule): a short oblique
 * hairline across the thread just before the follower note, where an engraver would put the accidental.
 */
export function adjustedTick(L: Pick<Layout, 'x' | 'y'>, b: Note, now: number): { x0: number; y0: number; x1: number; y1: number } {
  const cx = L.x(b.s, now) - 4.5, cy = L.y(b.p)
  return { x0: cx - 1.4, y0: cy + 2.6, x1: cx + 1.4, y1: cy - 2.6 }
}

/** Dotted threads from each leader note to its imitation, drawn once the follower note starts. */
export function drawThreads(ctx: CanvasRenderingContext2D, piece: Piece, L: Layout, now: number, muted?: ReadonlySet<number>) {
  const D = derive(piece)
  ctx.save()
  ctx.beginPath()
  ctx.rect(0, L.top - 6, L.width, L.bottom - L.top + 12)
  ctx.clip()
  ctx.strokeStyle = INK
  ctx.lineWidth = 0.6
  ctx.setLineDash([1, 2])
  const arch = (L.bottom - L.top) * 0.45
  for (const t of D.threads) {
    const a = piece.notes[t.a], b = piece.notes[t.b]
    if (b.s > now) break
    const ax = L.x(a.s + a.d / 2, now), bx = L.x(b.s + b.d / 2, now)
    if (!visible(L, ax, bx)) continue
    if (t.kind === 'retrograde' && Math.abs(bx - ax) > L.width * 1.2) continue
    const ay = L.y(a.p), by = L.y(b.p)
    ctx.globalAlpha = clamp01((now - b.s) / THREAD_FADE + 0.15) * (t.broken ? BROKEN_ALPHA : 1) * threadFade(piece, t, muted)
    ctx.beginPath()
    ctx.moveTo(ax, ay)
    if (t.kind === 'retrograde') {
      // the crab reads the line backwards: arches spanning the vertical mirror
      const h = Math.min(Math.abs(bx - ax) * 0.3, arch)
      ctx.bezierCurveTo(ax, ay - h, bx, by - h, bx, by)
    } else {
      // an S from leader to follower; a slight sag keeps unison threads from reading as rulings
      const c = Math.max(18, Math.abs(bx - ax) * 0.45)
      const sag = Math.min(10, Math.abs(bx - ax) * 0.05)
      ctx.bezierCurveTo(ax + c, ay + sag, bx - c, by + sag, bx, by)
    }
    ctx.stroke()
    if (t.adjusted && !t.broken) {
      const k = adjustedTick(L, b, now)
      ctx.setLineDash([])
      ctx.lineWidth = 0.9
      ctx.beginPath(); ctx.moveTo(k.x0, k.y0); ctx.lineTo(k.x1, k.y1); ctx.stroke()
      ctx.lineWidth = 0.6
      ctx.setLineDash([1, 2])
    }
  }
  ctx.restore()
}

/** The emphasis of an entry lasts this many beats after the entry ends. */
const EMPHASIS_TAIL = 1

/**
 * Engraved emphasis for fugue entries: while an entry sounds (until one beat after its end),
 * its notes up to the playhead (the sounding one included) are drawn with the heavy outline of a playing note.
 */
export function isEmphasised(piece: Piece, note: Note, now: number): boolean {
  const end = derive(piece).entryOf.get(note)
  return end !== undefined && note.s <= now && now < end + EMPHASIS_TAIL
}

/** A small engraved lozenge over the first note of each entry that has started. */
export function drawEntryOrnaments(ctx: CanvasRenderingContext2D, piece: Piece, L: Layout, now: number, muted?: ReadonlySet<number>) {
  const D = derive(piece)
  ctx.save()
  ctx.fillStyle = INK
  for (const [m, notes] of D.entryNotes) {
    const n = notes[0]
    if (!n || m.start > now) continue
    const x = L.x(n.s, now) + 3, y = L.y(n.p) - L.noteHeight / 2 - 4.5
    if (!visible(L, x, x)) continue
    ctx.globalAlpha = markFade(m, muted)
    ctx.beginPath()
    ctx.moveTo(x, y - 2.5); ctx.lineTo(x + 1.8, y); ctx.lineTo(x, y + 2.5); ctx.lineTo(x - 1.8, y)
    ctx.closePath(); ctx.fill()
  }
  ctx.restore()
}

/** The engraved annotations in the band above the roll. Each label drawn is added to `hits`, if given. */
export function drawAnnotations(
  ctx: CanvasRenderingContext2D, piece: Piece, L: Layout, now: number, muted?: ReadonlySet<number>, hits?: LabelHit[],
) {
  const sink = (mark: Mark | null): Sink => ({ hits, mark })
  const D = derive(piece)
  const band = L.band
  // every line first, every label last, so no line is printed over lettering
  const labels: (() => void)[] = []
  ctx.save()
  ctx.strokeStyle = INK
  ctx.lineWidth = 0.7
  ctx.setLineDash([])

  // mirror axes: the name at the left, on the line
  for (const m of piece.marks) {
    if (m.kind !== 'mirror-axis' || m.pitch == null || !m.label) continue
    const x0 = Math.max(-2, L.x(m.start, now)), x1 = Math.min(L.width + 2, L.x(m.end, now))
    if (x1 <= x0) continue
    const text = m.label, y = mirrorAxisY(L, m.pitch) - 3.5
    labels.push(() => label(ctx, text, Math.max(x0, 0) + 5, y, 'left', sink(m)))
  }

  // stretto groups: a bracket over the overlapping entries
  if (band.strettoY !== null) {
    for (const m of piece.marks) {
      if (m.kind !== 'stretto' || m.start > now) continue
      const x0 = L.x(m.start, now), x1 = L.x(m.end, now)
      if (!visible(L, x0, x1)) continue
      bracket(ctx, x0, x1, band.strettoY, 4)
      const y = band.strettoY - 3
      labels.push(() => fitLabel(ctx, 'stretto', x0, x1, y, sink(m)))
    }
  }

  // entries: a bracket each, all hung from one rail that runs back to the opening subject
  if (band.railY !== null && D.firstEntry) {
    const railY = band.railY, r = 5
    const first = D.firstEntry
    const started = [...D.entryNotes.keys()].filter(m => m.start <= now)
    const last = started[started.length - 1]
    const xf = L.x(first.start, now)
    if (last && last !== first && visible(L, xf, L.x(last.start, now))) {
      // off screen, the rail starts after a pointer naming the opening subject
      const pointer = railPointer(first, piece.beatsPerBar, xf, piece.pickup)
      let from = xf + r
      if (pointer) {
        ctx.font = LABEL_FONT
        from = 3 + ctx.measureText(pointer).width + 4
        labels.push(() => label(ctx, pointer, 3, railY + 3.5, 'left', sink(first)))
      }
      const to = L.x(last.start, now) - r
      if (to > from) hline(ctx, from, to, railY)
    }
    for (const m of started) {
      const x0 = L.x(m.start, now), x1 = L.x(m.end, now)
      const y = band.entryY.get(m)!
      if (!visible(L, x0 - r, x1)) continue
      ctx.globalAlpha = markFade(m, muted)
      bracket(ctx, x0, x1, y)
      // the drop from the rail, curving back towards the opening subject (each subject's
      // first entry, in a fugue on several subjects, curves forward and has its lozenge)
      const opening = D.openings.has(m)
      const dir = opening ? 1 : -1
      ctx.beginPath()
      ctx.moveTo(x0, y)
      ctx.lineTo(x0, railY + r)
      ctx.quadraticCurveTo(x0, railY, x0 + dir * r, railY)
      ctx.stroke()
      if (opening) {
        // a small lozenge marks the opening subject, where every link leads
        ctx.fillStyle = INK
        ctx.beginPath()
        ctx.moveTo(x0, railY - 3); ctx.lineTo(x0 + 2.2, railY); ctx.lineTo(x0, railY + 3); ctx.lineTo(x0 - 2.2, railY)
        ctx.closePath(); ctx.fill()
      }
      ctx.globalAlpha = 1
      const text = m.label
      if (text) labels.push(() => fitLabel(ctx, text, x0, x1, y - 2.5, sink(m)))
    }
  }

  // crab: the name over its vertical mirror
  for (const m of piece.marks) {
    if (m.kind !== 'crab-axis') continue
    const x = L.x(m.start, now)
    const text = `← ${m.label ?? 'cancrizans'} →`
    if (visible(L, x - 60, x + 60)) labels.push(() => label(ctx, text, x, band.labelY, 'center', sink(m)))
  }

  // per tonos: a rising stair of keys
  const rises = piece.marks.filter(m => m.kind === 'rise')
  rises.forEach((m, i) => {
    const x0 = L.x(m.start, now), x1 = L.x(m.end, now)
    if (!visible(L, x0, x1)) return
    const y = band.labelY + 6 - Math.min(i, 5) * 2
    ctx.globalAlpha = 1
    hline(ctx, x0, x1, y)
    if (i > 0) { ctx.beginPath(); ctx.moveTo(x0, y + 2); ctx.lineTo(x0, y); ctx.stroke() }
    const text = m.label
    if (text) labels.push(() => fitLabel(ctx, text, x0, x1, y - 3, sink(m)))
  })

  // augmentation / diminution: the leader's span solid, the stretch dotted
  for (const s of D.stretch) {
    if (s.start > now) break
    const x0 = L.x(s.start, now), xs = L.x(s.start + s.solid, now), x1 = L.x(s.start + s.full, now)
    if (!visible(L, x0, x1)) continue
    const y = band.labelY + 2
    ctx.setLineDash([])
    ctx.beginPath()
    ctx.moveTo(x0, y + 3); ctx.lineTo(x0, y); ctx.lineTo(xs, y); ctx.lineTo(xs, y + 2)
    ctx.stroke()
    ctx.setLineDash([1.5, 2])
    hline(ctx, xs, x1, y)
    ctx.setLineDash([])
    ctx.beginPath(); ctx.moveTo(x1, y); ctx.lineTo(x1, y + 3); ctx.stroke()
    const text = s.label
    if (text) labels.push(() => label(ctx, text, xs + 4, y - 3, 'left', sink(s.mark)))
  }
  for (const draw of labels) draw()
  ctx.restore()
}
