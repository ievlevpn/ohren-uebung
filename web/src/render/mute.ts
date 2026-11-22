import type { Mark, Piece, Thread } from '../model'

/** Opacity of everything that belongs to a muted voice. */
export const MUTED_ALPHA = 0.25

/** Opacity factor for voice `v`: faded when it is muted. */
export function fade(muted: ReadonlySet<number> | undefined, v: number | undefined): number {
  return v !== undefined && muted?.has(v) ? MUTED_ALPHA : 1
}

/** A thread is faded when either of its notes belongs to a muted voice. */
export function threadFade(piece: Piece, t: Thread, muted: ReadonlySet<number> | undefined): number {
  return Math.min(fade(muted, piece.notes[t.a]?.v), fade(muted, piece.notes[t.b]?.v))
}

/** A mark is faded when it names a muted voice (entries); marks without a voice never fade. */
export function markFade(m: Mark, muted: ReadonlySet<number> | undefined): number {
  return fade(muted, m.voice)
}
