import { DEFAULT_TUNING, tuningById, tuningFactor } from '../audio/shape'
import { smoothClock } from '../audio/playback'
import { getAudio } from '../audio/context'
import type { SoundHandle } from '../audio/sampler'
import type { Piece } from '../model'
import { exampleEnd } from './model'

export interface Sound { instrument: string; p: number; when: number; dur: number; pan: number }

/** Every note of an example as a sound starting at context time `t0`, at the example's (slow) tempo. */
export function exampleSounds(ex: Piece, t0: number): Sound[] {
  const spb = 60 / ex.tempo
  return ex.notes.map(n => ({
    instrument: ex.voices[n.v].instrument, p: n.p, when: t0 + n.s * spb, dur: n.d * spb, pan: ex.voices[n.v].pan,
  }))
}

interface Playing { ex: Piece; handles: SoundHandle[]; t0: number; timer: number; onEnd: () => void }
let current: Playing | null = null
/** Bumped by every stop: a load that finishes after a newer stop or play stays silent. */
let gen = 0

/** Stops the example that is sounding, if any. */
export function stopExample(): void {
  gen++
  if (!current) return
  const { ctx } = getAudio()
  for (const h of current.handles) h.release(ctx.currentTime)
  clearTimeout(current.timer)
  const end = current.onEnd
  current = null
  end()
}

/** Beats since the sounding example began (null if `ex` is not sounding). */
export function examplePosition(ex: Piece): number | null {
  if (!current || current.ex !== ex) return null
  return (exampleClock() - current.t0) * ex.tempo / 60
}
let clock: (() => number) | null = null
/** Smoothed audio clock for the example's moving cursor (Android steps the audio clock). */
function exampleClock(): number {
  clock ??= smoothClock(() => getAudio().ctx.currentTime, () => performance.now())
  return clock()
}

/**
 * Plays one example (stopping any other) on its voices' instruments. Call from a tap: the audio context
 * is resumed inside the gesture (iOS). `onEnd` runs when it finishes or is stopped.
 */
export async function playExample(ex: Piece, onEnd: () => void): Promise<void> {
  stopExample()
  const my = gen
  const { ctx, sampler } = getAudio()
  const resumed = ctx.state === 'running' ? Promise.resolve() : ctx.resume()
  const byInstr = new Map<string, number[]>()
  for (const n of ex.notes) {
    const ins = ex.voices[n.v].instrument
    byInstr.set(ins, [...(byInstr.get(ins) ?? []), n.p])
  }
  try {
    await Promise.all([resumed, ...[...byInstr].map(([ins, ps]) => sampler.load(ins, ps))])
  } catch (e) {
    if (my === gen) throw e
  }
  if (my !== gen) { onEnd(); return }
  const t0 = ctx.currentTime + 0.12
  const gain = 0.5 / Math.sqrt(ex.voices.length)
  // same tuning as the pieces, so an example over a ducked piece does not clash with it
  const tuning = tuningById(localStorage.getItem('fugue.tuning') ?? DEFAULT_TUNING)
  const handles = exampleSounds(ex, t0).map(s => sampler.play(s.instrument, s.p, s.when, s.dur, s.pan, gain, undefined,
    { tune: tuningFactor(s.p, tuning) }))
  const ms = (exampleEnd(ex) * 60 / ex.tempo + 0.4) * 1000
  current = { ex, handles, t0, onEnd, timer: window.setTimeout(() => { if (current?.ex === ex) { current = null; onEnd() } }, ms) }
}
