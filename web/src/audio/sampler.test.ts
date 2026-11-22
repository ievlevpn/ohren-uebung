import { describe, expect, it, test } from 'vitest'
import { Sampler, crossfadeLoop, loopPlan, nearestSample, type FetchLike } from './sampler'

const AVAIL = [48, 51, 54, 57, 60]

describe('nearestSample', () => {
  it('picks the closest and computes the rate', () => {
    const r = nearestSample(55, AVAIL)
    expect(r.sample).toBe(54)
    expect(r.rate).toBeCloseTo(2 ** (1 / 12), 9)
    const exact = nearestSample(57, AVAIL)
    expect(exact).toEqual({ sample: 57, rate: 1 })
    expect(nearestSample(53, AVAIL).rate).toBeCloseTo(2 ** (-1 / 12), 9)
  })
  it('out-of-range pitch uses nearest sample', () => {
    expect(nearestSample(80, AVAIL).sample).toBe(60)
    expect(nearestSample(80, AVAIL).rate).toBeCloseTo(2 ** (20 / 12), 9)
    expect(nearestSample(30, AVAIL).sample).toBe(48)
  })
  it('ties go to the lower sample; empty list throws', () => {
    expect(nearestSample(52.5, AVAIL).sample).toBe(51)
    expect(() => nearestSample(60, [])).toThrow()
  })
})

describe('loopPlan', () => {
  it('loops every sustaining instrument over the 30%-90% sustain of its buffer', () => {
    for (const ins of ['organ', 'flute', 'violin', 'viola', 'cello']) {
      expect(loopPlan(ins, 4)).toEqual({ loop: true, loopStart: 1.2, loopEnd: 3.6 })
    }
  })
  it('never loops the harpsichord (a plucked note decays)', () => {
    expect(loopPlan('harpsichord', 4).loop).toBe(false)
  })
})

describe('crossfadeLoop', () => {
  it('blends the end of the loop into the audio just before its start, so the jump back is seamless', () => {
    const d = Float32Array.from({ length: 20 }, (_, i) => i) // a ramp: every jump is audible
    crossfadeLoop(d, 8, 16, 4)
    // last sample before loopEnd ≈ sample before loopStart; then playback continues at loopStart
    const w = (k: number) => [Math.cos((k / 4) * Math.PI / 2), Math.sin((k / 4) * Math.PI / 2)]
    for (let k = 0; k < 4; k++) expect(d[12 + k]).toBeCloseTo((12 + k) * w(k)[0] + (4 + k) * w(k)[1], 5)
    expect(d[15]).toBeGreaterThan(7) // mostly the audio before loopStart by the end of the fade
    expect(d.slice(0, 12)).toEqual(Float32Array.from({ length: 12 }, (_, i) => i)) // outside the fade: untouched
  })
  it('keeps unrelated audio at the same loudness through the blend (equal power)', () => {
    let x = 7
    const rnd = () => { x = (x * 1103515245 + 12345) % 2147483648; return x / 2147483648 - 0.5 }
    const n = 40000, d = Float32Array.from({ length: n }, rnd)
    const before = Math.sqrt(d.slice(30000, 40000).reduce((p, v) => p + v * v, 0) / 10000)
    crossfadeLoop(d, 20000, 40000, 10000)
    const mid = Math.sqrt(d.slice(34000, 36000).reduce((p, v) => p + v * v, 0) / 2000)
    expect(mid / before).toBeGreaterThan(0.9) // a linear blend dips to ~0.71 here
  })
  it('clamps the fade to the audio available before loopStart', () => {
    const d = Float32Array.from({ length: 10 }, () => 1)
    expect(() => crossfadeLoop(d, 2, 9, 5)).not.toThrow()
  })
})

// ---- a fake Web Audio graph, just enough for Sampler.play ----
interface Ev { kind: string; v?: number; t: number }
function fakeParam() {
  const ev: Ev[] = []
  return {
    ev, value: 1,
    setValueAtTime(v: number, t: number) { ev.push({ kind: 'set', v, t }) },
    linearRampToValueAtTime(v: number, t: number) { ev.push({ kind: 'ramp', v, t }) },
    setTargetAtTime(v: number, t: number, tau: number) { ev.push({ kind: 'target', v, t, tau } as Ev) },
    cancelScheduledValues(t: number) { for (let i = ev.length - 1; i >= 0; i--) if (ev[i].t >= t) ev.splice(i, 1) },
  }
}
/** Gain at time t from the recorded automation (step / linear ramp), enough to see silence vs sound. */
function gainAt(ev: Ev[], t: number): number {
  let v = 1, prevT = 0
  for (const e of [...ev].sort((a, b) => a.t - b.t)) {
    if (e.t > t) { if (e.kind === 'ramp') return v + ((e.v! - v) * (t - prevT)) / (e.t - prevT); break }
    v = e.v!; prevT = e.t
  }
  return v
}
/** `stopThrows`: every stop() after the first throws (as a node that has already been stopped might). */
function fakeCtx(stopThrows = false) {
  const srcs: { stops: number[]; loop: boolean; loopStart: number; loopEnd: number }[] = []
  const gains: ReturnType<typeof fakeParam>[] = []
  const node = () => ({ connect: (x: unknown) => x, disconnect() {} })
  const ctx = {
    currentTime: 0,
    createBufferSource() {
      const s = { ...node(), buffer: null, playbackRate: { value: 1 }, loop: false, loopStart: 0, loopEnd: 0, onended: null, stops: [] as number[],
        start() {}, stop(t: number) { if (stopThrows && s.stops.length) throw new Error('InvalidStateError'); s.stops.push(t) } }
      srcs.push(s)
      return s
    },
    createGain() { const g = { ...node(), gain: fakeParam() }; gains.push(g.gain); return g },
    createStereoPanner() { return { ...node(), pan: { value: 0 } } },
    destination: {},
    async decodeAudioData() {
      const data = new Float32Array(4000)
      return { duration: 4, getChannelData: () => data, numberOfChannels: 1, sampleRate: 1000, length: 4000 }
    },
  }
  return { ctx: ctx as unknown as AudioContext, raw: ctx, srcs, gains }
}
const fetchFake: FetchLike = async () => ({
  ok: true, status: 200,
  json: async () => ({ violin: [60], harpsichord: [60] }),
  arrayBuffer: async () => new ArrayBuffer(8),
})

describe('Sampler.play', () => {
  it('a long violin note loops instead of running out of sample', async () => {
    const f = fakeCtx()
    const s = new Sampler(f.ctx, 'x/', fetchFake)
    await s.load('violin', [60])
    s.play('violin', 60, 1, 10, 0, 0.5)
    expect(f.srcs[0]).toMatchObject({ loop: true, loopStart: 1.2, loopEnd: 3.6 })
    expect(gainAt(f.gains[0].ev, 9)).toBeCloseTo(0.5, 9)
  })

  it('a cancelled note (released before it starts) is silenced even if stop() throws', async () => {
    const f = fakeCtx(true)
    const s = new Sampler(f.ctx, 'x/', fetchFake)
    await s.load('harpsichord', [60])
    const h = s.play('harpsichord', 60, 2, 1, 0, 0.5)
    expect(() => h.release(1)).not.toThrow()
    expect(gainAt(f.gains[0].ev, 2.5)).toBe(0)
  })

  it('a released note fades even if stop() throws', async () => {
    const f = fakeCtx(true)
    const s = new Sampler(f.ctx, 'x/', fetchFake)
    await s.load('harpsichord', [60])
    const h = s.play('harpsichord', 60, 0, 4, 0, 0.5)
    h.release(1)
    expect(gainAt(f.gains[0].ev, 1.5)).toBe(0)
  })

  it('a long harpsichord note rings on past its recording, fading, and is released at its written end', async () => {
    const f = fakeCtx()
    const s = new Sampler(f.ctx, 'x/', fetchFake)
    await s.load('harpsichord', [60])
    s.play('harpsichord', 60, 0, 8, 0, 0.5)
    const ev = f.gains[0].ev
    const fade = ev.find(e => e.kind === 'target')
    expect(fade).toBeDefined() // the envelope takes over the fade where the loop begins
    const atEnd = ev.find(e => e.kind === 'set' && e.t === 8)!
    expect(atEnd.v!).toBeGreaterThan(0) // still sounding at its written end…
    expect(atEnd.v!).toBeLessThan(0.5) // …quieter than it began
    expect(f.srcs[0].loop).toBe(true)
  })

  it('retime moves the end later or earlier', async () => {
    const f = fakeCtx()
    const s = new Sampler(f.ctx, 'x/', fetchFake)
    await s.load('violin', [60])
    const h = s.play('violin', 60, 0, 2, 0, 0.5)
    f.raw.currentTime = 1
    h.retime!(5)
    expect(gainAt(f.gains[0].ev, 4.5)).toBeCloseTo(0.5, 9)
    expect(gainAt(f.gains[0].ev, 5.5)).toBe(0)
    expect(f.srcs[0].stops.at(-1)).toBeGreaterThan(5)
    h.retime!(3)
    expect(gainAt(f.gains[0].ev, 3.5)).toBe(0)
  })
})

test('a plucked tail: its decay rate is measured, and evening it out leaves a level loop', async () => {
  const { measureDecay, flattenFrom } = await import('./sampler')
  const sr = 8000, n = sr * 3
  const d = new Float32Array(n)
  let x = 1
  for (let i = 0; i < n; i++) { x = (x * 1103515245 + 12345) % 2147483648; d[i] = (x / 2147483648 - 0.5) * 10 ** ((-15 * i / sr) / 20) } // noise falling 15 dB/s
  expect(measureDecay(d, sr, 1, 2.9)).toBeCloseTo(15, 0)
  flattenFrom(d, sr, 1, 15)
  expect(measureDecay(d, sr, 1, 2.9)).toBeLessThan(2.5) // clamped floor is 2: essentially level now
  const rms = (a: number, b: number) => Math.sqrt(d.slice(a * sr, b * sr).reduce((p, v) => p + v * v, 0) / ((b - a) * sr))
  expect(rms(1, 1.3) / rms(2.6, 2.9)).toBeGreaterThan(0.85)
  expect(rms(1, 1.3) / rms(2.6, 2.9)).toBeLessThan(1.15)
})

test('held harpsichord notes ring like a real string: long in the bass, short in the treble', async () => {
  const { ringDecay } = await import('./sampler')
  expect(60 / ringDecay(45)).toBeGreaterThan(12) // a low A rings well over 12 s
  expect(60 / ringDecay(84)).toBeLessThan(4)
  expect(ringDecay(20)).toBe(ringDecay(29))
  expect(ringDecay(100)).toBe(ringDecay(89))
  for (let p = 30; p < 90; p++) expect(ringDecay(p)).toBeGreaterThanOrEqual(ringDecay(p - 1))
})
