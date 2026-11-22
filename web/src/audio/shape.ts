/** How the notes are performed: tuning, note shapes, accents, the room. Bach's notes stay as written. */

export interface Tuning { id: string; name: string; a4: number; cents: number[] } // cents: per pitch class C..B, from equal, A = 0

export const TUNINGS: Tuning[] = [
  { id: 'equal', name: 'equal · a′ 440', a4: 440, cents: [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
  // Vallotti: six fifths tempered by 1/6 comma (F–C–G–D–A–E–B), six pure
  { id: 'vallotti', name: 'Vallotti · a′ 415', a4: 415, cents: [5.9, 0, 2.0, 3.9, -2.0, 7.8, -2.0, 3.9, 2.0, 0, 5.9, -3.9] },
  // Werckmeister III: four fifths tempered by 1/4 comma (C–G–D–A, B–F♯)
  { id: 'werckmeister', name: 'Werckmeister III · a′ 415', a4: 415, cents: [11.7, 1.9, 3.9, 5.9, 1.9, 9.8, 0, 7.8, 3.9, 0, 7.8, 3.9] },
]
export const DEFAULT_TUNING = 'vallotti'

export function tuningById(id: string): Tuning {
  return TUNINGS.find(t => t.id === id) ?? TUNINGS[0]
}

/** Playback-rate factor that moves an equal-tempered a′ 440 pitch to `tuning`. */
export function tuningFactor(pitch: number, tuning: Tuning): number {
  const pc = ((pitch % 12) + 12) % 12
  return (tuning.a4 / 440) * 2 ** (tuning.cents[pc] / 1200)
}

/** Seconds of fade-in and fade-out per instrument when shaped; plain playing is a hard start and a 0.08 s fade. */
export interface Envelope { attack: number; release: number }
export const PLAIN: Envelope = { attack: 0, release: 0.08 }
const SHAPED: Record<string, Envelope> = {
  harpsichord: { attack: 0, release: 0.18 }, // the damper falls: a short ring after the key is let go
  organ: { attack: 0.012, release: 0.12 },
  flute: { attack: 0.03, release: 0.22 },
  violin: { attack: 0.04, release: 0.3 },
  viola: { attack: 0.04, release: 0.3 },
  cello: { attack: 0.045, release: 0.32 },
}
export function envelopeFor(instrument: string, shaped: boolean): Envelope {
  return shaped ? SHAPED[instrument] ?? PLAIN : PLAIN
}

/**
 * Loudness factor for a note starting at beat `s`: the bar's first beat a little stronger, notes between beats a
 * little lighter. Harpsichord and organ cannot play louder or softer, so they always get 1.
 */
export function accent(s: number, beatsPerBar: number, pickup: number, instrument: string): number {
  if (instrument === 'harpsichord' || instrument === 'organ') return 1
  const eps = 1e-6
  const inBar = (((s - pickup) % beatsPerBar) + beatsPerBar) % beatsPerBar
  if (inBar < eps || beatsPerBar - inBar < eps) return 1.15
  return Math.abs(s - Math.round(s)) < eps ? 1 : 0.9
}

/** The closing notes (those still sounding at the end) are held this much longer, like a written fermata. */
export const FINAL_HOLD = 1.6

/** How much of the room the listener hears, per instrument family. */
export function roomLevel(instruments: string[]): number {
  if (instruments.every(i => i === 'harpsichord')) return 0.3
  if (instruments.some(i => i === 'organ')) return 0.55
  return 0.42
}

/**
 * A synthetic hall: stereo noise with an exponential decay to −60 dB over `seconds`, darkening as it fades
 * (high frequencies die first, as in a stone room), after a short pre-delay.
 */
export function impulse(sampleRate: number, seconds: number, seed = 1): Float32Array[] {
  const pre = Math.round(0.018 * sampleRate)
  const n = pre + Math.round(seconds * sampleRate)
  let x = seed >>> 0
  const rnd = () => { x = (x * 1664525 + 1013904223) >>> 0; return x / 2 ** 31 - 1 }
  return [0, 1].map(() => {
    const d = new Float32Array(n)
    let lp = 0
    for (let i = pre; i < n; i++) {
      const t = (i - pre) / sampleRate
      const k = Math.min(0.92, 0.25 + 0.7 * (t / seconds)) // one-pole low-pass, closing over time
      lp = lp * k + rnd() * (1 - k)
      d[i] = lp * Math.exp((-6.9 * t) / seconds)
    }
    return d
  })
}

/** The room as Web Audio nodes: `input` → dry + convolved wet → `out`. */
export function makeRoom(ctx: BaseAudioContext, out: AudioNode, seconds = 2.2) {
  const input = ctx.createGain()
  const dry = ctx.createGain()
  const wet = ctx.createGain()
  const conv = ctx.createConvolver()
  const chans = impulse(ctx.sampleRate, seconds)
  const buf = ctx.createBuffer(2, chans[0].length, ctx.sampleRate)
  chans.forEach((c, i) => buf.copyToChannel(c as Float32Array<ArrayBuffer>, i))
  conv.buffer = buf
  input.connect(dry).connect(out)
  input.connect(conv).connect(wet).connect(out)
  wet.gain.value = 0
  return {
    input,
    setLevel(level: number) { wet.gain.value = level; dry.gain.value = 1 - level * 0.35 },
    disconnect() { input.disconnect(); dry.disconnect(); wet.disconnect(); conv.disconnect() },
  }
}
