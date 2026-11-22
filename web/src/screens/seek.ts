import { barOf, type Piece } from '../model'

type Bars = Pick<Piece, 'beatsPerBar' | 'pickup'>

/** Beat where bar `n` begins (bar 1 starts after the upbeat; bar 0 is the upbeat itself, starting at 0). */
export function barStart(p: Bars, n: number): number {
  return n <= 0 ? 0 : (p.pickup ?? 0) + (n - 1) * p.beatsPerBar
}

/** Back one bar: to the start of the current bar, or of the previous one if already within half a beat of it. */
export function prevBarBeat(p: Bars, beat: number): number {
  const n = barOf(p, beat)
  const s = barStart(p, n)
  return beat - s > 0.5 ? s : barStart(p, n - 1)
}

/** Forward one bar: the start of the next bar, never past `last`. */
export function nextBarBeat(p: Bars, beat: number, last: number): number {
  return Math.min(barStart(p, barOf(p, beat) + 1), last)
}

/** A loop over whole bars, from the bar containing `a` to the end of the bar containing `b` (in either order). */
export function loopRange(p: Bars, a: number, b: number, last: number): { from: number; to: number; bars: [number, number] } {
  const n1 = Math.min(barOf(p, a), barOf(p, b)), n2 = Math.max(barOf(p, a), barOf(p, b))
  return { from: barStart(p, n1), to: Math.min(barStart(p, n2 + 1), last), bars: [Math.max(1, n1), n2] }
}

/** Beat reached by dragging the roll `dx` CSS px from `beat` (dragging right brings earlier music back). */
export function dragBeat(beat: number, dx: number, beatWidth: number, last: number): number {
  return Math.min(last, Math.max(0, beat - dx / beatWidth))
}
