import type { Mark, Piece } from '../model'

/** Below this width (CSS px) the roll is laid out for a phone: playhead at 40 %. */
export const PHONE_WIDTH = 600
export const MIN_NOTE_HEIGHT = 6
const MAX_NOTE_HEIGHT = 13
/** A pitch row never grows taller than this; small ranges are centred instead. */
const MAX_ROW = 18
/** Semitones of paper kept above the highest and below the lowest note. */
const PITCH_MARGIN = 2
/** Space under the roll for the *nunc* label. */
const FOOT = 24
/** Height of one row in the band of engraved annotations above the roll. */
export const BAND_ROW = 13

/** Where the annotations above the roll go (y in CSS px from the canvas top). */
export interface Band {
  /** Stretto brackets (fugues with stretto marks). */
  strettoY: number | null
  /** The rail linking every entry back to the opening subject. */
  railY: number | null
  /** y of the bracket row for each entry mark, keyed by the mark. */
  entryY: Map<Mark, number>
  /** A general line for canon labels (crab, rises, stretch brackets). */
  labelY: number
  height: number
}

export interface Layout {
  width: number
  height: number
  dpr: number
  phone: boolean
  /** x of the fixed playhead (CSS px). */
  playheadX: number
  /** Top and bottom of the note area (CSS px); the band sits above `top`. */
  top: number
  bottom: number
  band: Band
  /** Lowest and highest pitch rows drawn (margins included). */
  lo: number
  hi: number
  rowHeight: number
  noteHeight: number
  /** CSS px per beat. */
  beatWidth: number
  /** x of a beat when the playhead is at `now`. */
  x(beat: number, now: number): number
  /** y of the centre of a pitch row. */
  y(pitch: number): number
}

/** Greedy rows for overlapping entries: each entry takes the first row free at its start. */
export function entryRows(marks: Mark[]): Map<Mark, number> {
  const entries = marks.filter(m => m.kind === 'entry').sort((a, b) => a.start - b.start)
  const rowEnds: number[] = []
  const rows = new Map<Mark, number>()
  for (const e of entries) {
    let r = rowEnds.findIndex(end => end <= e.start)
    if (r < 0) { r = rowEnds.length; rowEnds.push(0) }
    rowEnds[r] = e.end
    rows.set(e, r)
  }
  return rows
}

function bandFor(piece: Piece): Band {
  const rows = entryRows(piece.marks)
  const hasStretto = piece.marks.some(m => m.kind === 'stretto')
  let y = 8
  const strettoY = hasStretto ? y + 6 : null
  if (hasStretto) y += BAND_ROW
  if (rows.size === 0) {
    const labelY = y + 12
    return { strettoY, railY: null, entryY: new Map(), labelY, height: labelY + 12 }
  }
  const railY = y + 6
  y += 10
  const entryY = new Map<Mark, number>()
  let maxRow = 0
  for (const [m, r] of rows) {
    entryY.set(m, y + BAND_ROW * (r + 1))
    maxRow = Math.max(maxRow, r)
  }
  const last = y + BAND_ROW * (maxRow + 1)
  return { strettoY, railY, entryY, labelY: last, height: last + 10 }
}

/** Pixels per second of scrolling: calm, a little faster on wide screens. */
function scrollSpeed(width: number): number {
  return Math.min(100, Math.max(36, width * 0.1))
}

/** `foot`: paper kept under the notes (the roll's *nunc* label; a glossary figure needs less). */
export function layoutFor(piece: Piece, width: number, height: number, dpr: number, foot = FOOT): Layout {
  const phone = width < PHONE_WIDTH
  const playheadX = width * (phone ? 0.4 : 0.5)
  const band = bandFor(piece)

  let pmin = Infinity, pmax = -Infinity
  for (const n of piece.notes) { if (n.p < pmin) pmin = n.p; if (n.p > pmax) pmax = n.p }
  if (!isFinite(pmin)) { pmin = 60; pmax = 72 }
  const lo = pmin - PITCH_MARGIN, hi = pmax + PITCH_MARGIN
  const rows = hi - lo + 1

  let top = band.height
  let bottom = height - foot
  const avail = Math.max(1, bottom - top)
  const rowHeight = Math.min(MAX_ROW, avail / rows)
  // centre a small range in the space it does not fill
  const slack = avail - rowHeight * rows
  top += slack / 2
  bottom = top + rowHeight * rows
  // shift the band down with the notes so annotations stay close to the music
  if (slack > 0) {
    const d = slack / 2
    band.strettoY = band.strettoY === null ? null : band.strettoY + d
    band.railY = band.railY === null ? null : band.railY + d
    for (const [m, y] of band.entryY) band.entryY.set(m, y + d)
    band.labelY += d
    band.height += d
  }

  const noteHeight = Math.min(MAX_NOTE_HEIGHT, Math.max(MIN_NOTE_HEIGHT, rowHeight * 0.9))
  const beatWidth = scrollSpeed(width) * 60 / piece.tempo
  const rowTop = top

  return {
    width, height, dpr, phone, playheadX, top, bottom, band, lo, hi, rowHeight, noteHeight, beatWidth,
    x: (beat, now) => playheadX + (beat - now) * beatWidth,
    y: pitch => rowTop + (hi - pitch + 0.5) * rowHeight,
  }
}

/** Canvas pixel density: the screen's, but at most 2 — above that the roll looks the same and costs far more to paint. */
export function canvasDpr(screenDpr: number | undefined): number {
  return Math.min(2, screenDpr || 1)
}

/** Shortest gap between two frames of the scrolling roll (ms): about 60 per second, also on 90/120 Hz screens. */
export const FRAME_MS = 1000 / 62
