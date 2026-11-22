export type EnsembleId = 'chamber' | 'harpsichord' | 'strings' | 'organ'
export type Texture = 'solid' | 'hatch' | 'stipple' | 'dashed' | 'open' | 'cross'
export type ThreadKind = 'imitation' | 'mirror' | 'retrograde' | 'stretch'
export type MarkKind = 'mirror-axis' | 'crab-axis' | 'stretch' | 'rise' | 'entry' | 'stretto'
/** An entry mark's label is its form, plus its transform ("motive inverted"), plus " (head)"
 * for a statement of the subject's head alone ("subject (head)"). Fugues use
 * subject/answer/countersubject; inventions motive/countermotive. */
export type EntryForm = 'subject' | 'answer' | 'countersubject' | 'motive' | 'countermotive'

/** v: voice index, p: MIDI pitch, s/d: start and duration in beats. c: a secondary note of its voice (a lower
 * chord tone or a split-off line): played and drawn, but never part of an entry or a thread. Absent: false. */
export interface Note { v: number; p: number; s: number; d: number; c?: boolean }
export interface Voice { name: string; texture: Texture; instrument: string; pan: number }
/** a, b: note indices. adjusted: pitch differs from the rule's prediction within tolerance (not broken). */
export interface Thread { a: number; b: number; kind: ThreadKind; broken: boolean; adjusted: boolean }
export interface Mark {
  kind: MarkKind; start: number; end: number
  voice?: number; pitch?: number; label?: string
}
export interface Caption { at: number; text: string }

export interface Piece {
  id: string; title: string; collection: string; catalogue: string; key: string
  tempo: number; beatsPerBar: number; ensemble: string
  voices: Voice[]; notes: Note[]; threads: Thread[]; marks: Mark[]; captions: Caption[]
  techniques: string[]; listenFor: string
  /** The beat in quarter notes (1 = ♩, 0.5 = ♪, 0.75 = ♪.); tempo counts these beats. Absent: 1. */
  beatUnit?: number
  /** Beats of upbeat before bar 1 (bar n starts at pickup + (n-1)·beatsPerBar). Absent: 0. */
  pickup?: number
  /** Glossary entry id -> the "In this piece" line on that entry's card (markings glossary_notes). Absent: none. */
  glossaryNotes?: Record<string, string>
}

/** Bach's bar number of a beat; an upbeat is bar 0. */
export function barOf(piece: Pick<Piece, 'beatsPerBar' | 'pickup'>, beat: number): number {
  return Math.floor((beat - (piece.pickup ?? 0)) / piece.beatsPerBar) + 1
}

export interface Collection {
  id: string; numeral: string; name: string; catalogue: string; note: string
  books: { name: string; pieces: string[] }[]
}
export interface PieceSummary {
  id: string; title: string; collection: string; catalogue: string; key: string
  voices: number; bars: number; techniques: string[]; listenFor: string
  /** The piece's own number in its book (WTC fugue 3), shown instead of its place in the list. */
  number?: number
}
export interface Library {
  collections: Collection[]
  pieces: PieceSummary[]
  techniques: Record<string, string[]>
}

const STRINGS = ['id', 'title', 'collection', 'catalogue', 'key', 'ensemble', 'listenFor'] as const
const NUMBERS = ['tempo', 'beatsPerBar'] as const
const ARRAYS = ['voices', 'notes', 'threads', 'marks', 'captions', 'techniques'] as const

/** Checks the top-level shape and throws on a missing or mistyped field. */
export function parsePiece(json: unknown): Piece {
  if (typeof json !== 'object' || json === null) throw new Error('piece: not an object')
  const o = json as Record<string, unknown>
  for (const k of STRINGS) if (typeof o[k] !== 'string') throw new Error(`piece: missing string field '${k}'`)
  for (const k of NUMBERS) if (typeof o[k] !== 'number') throw new Error(`piece: missing number field '${k}'`)
  for (const k of ARRAYS) if (!Array.isArray(o[k])) throw new Error(`piece: missing array field '${k}'`)
  if ((o.voices as unknown[]).length === 0) throw new Error("piece: 'voices' is empty")
  return json as Piece
}
