/** Result of choosing a sample for a pitch: play `sample` at `rate` (= 2^((pitch - sample)/12)). */
export interface SampleChoice { sample: number; rate: number }

/** Nearest available sample (MIDI numbers); ties go to the lower sample. Out-of-range pitches use the end sample. */
export function nearestSample(pitch: number, available: number[]): SampleChoice {
  if (available.length === 0) throw new Error('nearestSample: no samples available')
  let best = available[0]
  for (const s of available) {
    const d = Math.abs(s - pitch), bd = Math.abs(best - pitch)
    if (d < bd || (d === bd && s < best)) best = s
  }
  return { sample: best, rate: 2 ** ((pitch - best) / 12) }
}

const RELEASE = 0.08 // seconds, linear fade after a note's written end (plain playing)

/** Per-note performance: `tune` multiplies the playback rate (temperament, pitch level); attack/release in seconds. */
export interface NoteShape { tune?: number; attack?: number; release?: number }
/** Plucked instruments decay naturally and are never looped; every sustaining instrument is. */
const DECAYING = new Set(['harpsichord'])
const LOOP_FROM = 0.3, LOOP_TO = 0.9 // fractions of the buffer (FluidR3 sustains are level from ~0.5 s to the end)
const LOOP_FADE = 0.1 // seconds of crossfade at the loop seam

export interface LoopPlan { loop: boolean; loopStart?: number; loopEnd?: number }

/** Plucked notes longer than their recording: from RING_FROM s the tail is evened out and looped up to RING_TO s,
 * and the fade is applied by the envelope at the rate measured in the recording, so the string rings on as written. */
export const RING_FROM = 1.6, RING_TO = 3.05
const DB = 20 / Math.LN10 // dB per neper: level(t) = exp(-t/tau) falls DB/tau dB per second

/** Decay of a recording between `from` and `to` s, in dB per second (a least-squares line through 0.1 s RMS windows),
 * clamped to 2…60 dB/s. */
export function measureDecay(data: Float32Array, sampleRate: number, from: number, to: number): number {
  const win = Math.round(0.1 * sampleRate)
  const xs: number[] = [], ys: number[] = []
  for (let a = Math.round(from * sampleRate); a + win <= Math.min(data.length, Math.round(to * sampleRate)); a += win) {
    let e = 0
    for (let i = a; i < a + win; i++) e += data[i] * data[i]
    xs.push(a / sampleRate); ys.push(10 * Math.log10(e / win + 1e-20))
  }
  if (xs.length < 2) return 20
  const mx = xs.reduce((p, x) => p + x, 0) / xs.length, my = ys.reduce((p, y) => p + y, 0) / ys.length
  let num = 0, den = 0
  for (let i = 0; i < xs.length; i++) { num += (xs[i] - mx) * (ys[i] - my); den += (xs[i] - mx) ** 2 }
  return Math.min(60, Math.max(2, -num / den))
}

/** Undoes a decay of `dbPerSec` from `from` s onwards, so the rest of the buffer stays at the level it had there. */
export function flattenFrom(data: Float32Array, sampleRate: number, from: number, dbPerSec: number): void {
  const a = Math.round(from * sampleRate)
  for (let i = a; i < data.length; i++) data[i] *= 10 ** ((dbPerSec * ((i - a) / sampleRate)) / 20)
}

interface Ring { from: number; to: number; dbPerSec: number }

/** How long a real harpsichord string rings before it is inaudible (−60 dB), by pitch: long in the bass, short in the
 * treble. The recordings fade much faster than this, so once a held note passes its recording's first RING_FROM s
 * it fades at the instrument's rate instead (never slower than the recording would have). */
const RING_T60: [number, number][] = [[29, 22], [41, 16], [53, 11], [65, 7], [77, 4.5], [89, 3]]
export function ringDecay(pitch: number): number {
  const t = RING_T60
  if (pitch <= t[0][0]) return 60 / t[0][1]
  for (let i = 1; i < t.length; i++) {
    if (pitch <= t[i][0]) {
      const [p0, s0] = t[i - 1], [p1, s1] = t[i]
      return 60 / (s0 + ((s1 - s0) * (pitch - p0)) / (p1 - p0))
    }
  }
  return 60 / t[t.length - 1][1]
}

/**
 * Sustaining instruments (all but the harpsichord) loop the sustain portion of the buffer, 30 % to 90 % of its
 * length, so a held note sounds for as long as it is written (the samples themselves last ≈3.1 s). Looping is always
 * on for them: playback only reaches the loop on notes that need it, and a tempo change may lengthen a sounding note.
 */
export function loopPlan(instrument: string, bufferSec: number): LoopPlan {
  if (DECAYING.has(instrument)) return { loop: false }
  return { loop: true, loopStart: bufferSec * LOOP_FROM, loopEnd: bufferSec * LOOP_TO }
}

/**
 * Makes the jump from `end` back to `start` (sample indices) seamless: the `fade` samples before `end` are crossfaded
 * into the `fade` samples before `start`, so the audio leading up to the jump continues into `start` as it would have
 * originally. In place; `fade` is clamped to what fits.
 */
export function crossfadeLoop(data: Float32Array, start: number, end: number, fade: number): void {
  const n = Math.max(0, Math.min(fade, start, end - start))
  for (let i = 0; i < n; i++) {
    const t = (i / n) * (Math.PI / 2) // equal power: two unrelated stretches keep their loudness through the blend
    data[end - n + i] = data[end - n + i] * Math.cos(t) + data[start - n + i] * Math.sin(t)
  }
}

export interface SoundHandle { release(at: number): void; retime(end: number): void }
export type FetchLike = (url: string) => Promise<{ ok: boolean; status: number; json(): Promise<unknown>; arrayBuffer(): Promise<ArrayBuffer> }>

/** Web Audio sample player. Samples live in `<baseUrl>/<instrument>/<midi>.mp3`, listed by `<baseUrl>/index.json`. */
export class Sampler {
  private index: Record<string, number[]> | null = null
  private buffers = new Map<string, AudioBuffer>() // `${instrument}/${midi}`
  private rings = new Map<string, Ring>() // plucked samples prepared to ring on

  private ctx: AudioContext
  private baseUrl: string
  private fetchFn: FetchLike

  constructor(ctx: AudioContext, baseUrl = 'samples/', fetchFn: FetchLike = (u) => fetch(u)) {
    this.ctx = ctx
    this.baseUrl = baseUrl
    this.fetchFn = fetchFn
  }

  private async getIndex(): Promise<Record<string, number[]>> {
    if (!this.index) {
      const r = await this.fetchFn(`${this.baseUrl}index.json`)
      if (!r.ok) throw new Error(`samples index: HTTP ${r.status}`)
      this.index = (await r.json()) as Record<string, number[]>
    }
    return this.index
  }

  /** Loads only the samples needed for `pitches` on `instrument`. */
  async load(instrument: string, pitches: number[]): Promise<void> {
    const avail = (await this.getIndex())[instrument]
    if (!avail) throw new Error(`no samples for instrument '${instrument}'`)
    const need = new Set(pitches.map((p) => nearestSample(p, avail).sample))
    await Promise.all([...need].map(async (m) => {
      const key = `${instrument}/${m}`
      if (this.buffers.has(key)) return
      const r = await this.fetchFn(`${this.baseUrl}${key}.mp3`)
      if (!r.ok) throw new Error(`sample ${key}: HTTP ${r.status}`)
      const buf = await this.ctx.decodeAudioData(await r.arrayBuffer())
      const plan = loopPlan(instrument, buf.duration)
      if (plan.loop) {
        const sr = buf.sampleRate
        for (let c = 0; c < buf.numberOfChannels; c++) {
          crossfadeLoop(buf.getChannelData(c), Math.round(plan.loopStart! * sr), Math.round(plan.loopEnd! * sr), Math.round(LOOP_FADE * sr))
        }
      }
      if (DECAYING.has(instrument) && buf.duration > RING_TO + 0.05) {
        const sr = buf.sampleRate
        const db = measureDecay(buf.getChannelData(0), sr, RING_FROM, RING_TO)
        for (let c = 0; c < buf.numberOfChannels; c++) {
          const d = buf.getChannelData(c)
          flattenFrom(d, sr, RING_FROM, db)
          crossfadeLoop(d, Math.round(RING_FROM * sr), Math.round(RING_TO * sr), Math.round(LOOP_FADE * sr))
        }
        this.rings.set(key, { from: RING_FROM, to: RING_TO, dbPerSec: db })
      }
      this.buffers.set(key, buf)
    }))
  }

  /** Plays one note at context time `when` for `duration` s, into `out` (default: the speakers).
   * Returns a handle to release it early. */
  play(instrument: string, pitch: number, when: number, duration: number, pan: number, gain: number,
    out: AudioNode = this.ctx.destination, shape: NoteShape = {}): SoundHandle {
    const release = shape.release ?? RELEASE
    const attack = Math.min(shape.attack ?? 0, duration / 2)
    const avail = this.index?.[instrument]
    if (!avail) throw new Error(`sampler: '${instrument}' not loaded`)
    const { sample, rate } = nearestSample(pitch, avail)
    const buffer = this.buffers.get(`${instrument}/${sample}`)
    if (!buffer) throw new Error(`sampler: sample ${instrument}/${sample} not loaded`)
    const ctx = this.ctx
    const src = ctx.createBufferSource()
    src.buffer = buffer
    src.playbackRate.value = rate * (shape.tune ?? 1)
    const plan = loopPlan(instrument, buffer.duration)
    if (plan.loop) { src.loop = true; src.loopStart = plan.loopStart!; src.loopEnd = plan.loopEnd! }
    // a plucked string held longer than its recording rings on, fading at the recording's own rate
    const ring = this.rings.get(`${instrument}/${sample}`)
    const speed = src.playbackRate.value
    const fadeAt = ring ? when + ring.from / speed : Infinity
    const tau = ring ? DB / Math.min(ring.dbPerSec * speed, ringDecay(pitch)) : Infinity
    if (ring) { src.loop = true; src.loopStart = ring.from; src.loopEnd = ring.to }
    /** The envelope's level at time t (before any release). */
    const level = (t: number) => (t <= fadeAt ? gain : gain * Math.exp(-(t - fadeAt) / tau))
    const env = ctx.createGain()
    if (attack > 0) {
      env.gain.setValueAtTime(0, when)
      env.gain.linearRampToValueAtTime(gain, when + attack)
    } else env.gain.setValueAtTime(gain, when)
    const panner = ctx.createStereoPanner()
    panner.pan.value = pan
    src.connect(env).connect(panner).connect(out)
    let end = when + duration
    if (end > fadeAt) { env.gain.setValueAtTime(gain, fadeAt); env.gain.setTargetAtTime(0, fadeAt, tau) }
    env.gain.setValueAtTime(level(end), end)
    env.gain.linearRampToValueAtTime(0, end + release)
    src.start(when)
    src.stop(end + release)
    src.onended = () => { src.disconnect(); env.disconnect(); panner.disconnect() }
    const stop = (t: number) => { try { src.stop(t) } catch { /* already stopped: the gain is already at zero */ } }
    /** Ends the note at `t` (a short fade). The gain is set first so a throwing stop() cannot leave it sounding. */
    const endAt = (t: number) => {
      if (t <= when) { // never sounds
        env.gain.cancelScheduledValues(0)
        env.gain.setValueAtTime(0, 0)
        stop(when)
        end = when
        return
      }
      env.gain.cancelScheduledValues(Math.min(t, end))
      env.gain.setValueAtTime(level(t), t)
      env.gain.linearRampToValueAtTime(0, t + release)
      stop(t + release)
      end = t
    }
    return {
      release: (at) => { if (at < end) endAt(at) }, // past the written end it is already ending on its own
      retime: (to) => { if (end > ctx.currentTime) endAt(Math.max(to, ctx.currentTime)) }, // only while still held
    }
  }
}

/** Minimal context surface used by `unlockAudio`. */
export interface ResumableContext { state: string; resume(): Promise<void> }

/**
 * iOS: an AudioContext starts suspended and only a real activation (touchend, click, keydown; not
 * pointerdown/touchstart) may resume it. Listeners stay until the context is actually running, so a
 * resume that does not take effect is retried on the next gesture.
 */
export function unlockAudio(ctx: ResumableContext, target: EventTarget = document): void {
  const events = ['touchend', 'click', 'keydown']
  const cleanup = () => { for (const e of events) target.removeEventListener(e, unlock) }
  const unlock = () => {
    void ctx.resume().then(() => { if (ctx.state === 'running') cleanup() }, () => { /* retry on next gesture */ })
  }
  for (const e of events) target.addEventListener(e, unlock)
}

/** Calls `pause` when the page becomes hidden (tab switch, screen lock). Returns an unsubscribe function. */
export function pauseWhenHidden(pause: () => void, doc: Document = document): () => void {
  const h = () => { if (doc.visibilityState === 'hidden') pause() }
  doc.addEventListener('visibilitychange', h)
  return () => doc.removeEventListener('visibilitychange', h)
}
