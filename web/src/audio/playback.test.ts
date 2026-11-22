import { expect, test } from 'vitest'
import { LoadGate, heardPosition } from './playback'

test('only the latest load may finish: an older load that ends later is ignored', () => {
  const gate = new LoadGate()
  expect(gate.loading).toBe(false)
  const a = gate.begin()   // switch to ensemble A
  const b = gate.begin()   // quickly switch to B
  expect(gate.loading).toBe(true)
  expect(gate.finish(a)).toBe(false) // A done while B in flight: Play stays disabled
  expect(gate.loading).toBe(true)
  const c = gate.begin()
  expect(gate.finish(b)).toBe(false)
  expect(gate.finish(c)).toBe(true)
  expect(gate.loading).toBe(false)
  expect(gate.finish(c)).toBe(false) // finishing twice is a no-op
})

test('a failed latest load is reported, an older failure is not', () => {
  const gate = new LoadGate()
  const a = gate.begin()
  const b = gate.begin()
  expect(gate.fail(a)).toBe(false)
  expect(gate.failed).toBe(false)
  expect(gate.fail(b)).toBe(true)
  expect(gate.failed).toBe(true)
  expect(gate.loading).toBe(false)
  gate.begin() // retry clears the failure
  expect(gate.failed).toBe(false)
})

test('the roll is drawn at the position being heard, behind the scheduler by the output latency', () => {
  expect(heardPosition(10, 0.1, 60)).toBeCloseTo(9.9)
  expect(heardPosition(10, 0.1, 120)).toBeCloseTo(9.8)
  expect(heardPosition(0.05, 0.2, 60)).toBe(0)   // never before the start
  expect(heardPosition(4, 0, 84)).toBe(4)
  expect(heardPosition(4, NaN, 84)).toBe(4)      // unknown latency
})

test('smoothClock fills in between coarse audio-clock steps, capped and never backwards', async () => {
  const { smoothClock } = await import('./playback')
  let audio = 1, wall = 0
  const c = smoothClock(() => audio, () => wall)
  expect(c()).toBe(1)
  wall = 10; expect(c()).toBeCloseTo(1.01)
  wall = 20; expect(c()).toBeCloseTo(1.02)
  wall = 500; expect(c()).toBeCloseTo(1.12) // the audio clock stalled: no running away
  audio = 1.04; wall = 510; expect(c()).toBeCloseTo(1.12) // a step behind the estimate holds still
  wall = 600; expect(c()).toBeCloseTo(1.13)
  audio = 5; wall = 610; expect(c()).toBe(5) // a jump (seek, resume) is taken at once
})

test('positionFilter: follows steady playback, never moves back, snaps on seeks', async () => {
  const { positionFilter } = await import('./playback')
  const f = positionFilter()
  const bps = 2 // 120 bpm
  let ms = 0
  expect(f.next(10, ms, bps)).toBe(10)
  // the clock stalls at the start: nothing moves
  ms += 16; expect(f.next(10, ms, bps)).toBe(10)
  // steady playback: tracks the target closely
  let t = 10, out = 10
  for (let i = 0; i < 120; i++) { ms += 16; t += bps * 0.016; out = f.next(t, ms, bps) }
  expect(Math.abs(out - t)).toBeLessThan(0.02)
  // the browser revises its latency: the target jumps back 0.2 beat; the roll does not go backwards
  const before = out
  ms += 16; t += bps * 0.016 - 0.2
  const after = f.next(t, ms, bps)
  expect(after).toBeGreaterThanOrEqual(before)
  // ...and catches up smoothly: speed never off by more than a quarter, back in step within ~1.5 s
  let prev = after
  for (let i = 0; i < 95; i++) {
    ms += 16; t += bps * 0.016; out = f.next(t, ms, bps)
    expect(out - prev).toBeGreaterThanOrEqual(0.75 * bps * 0.016 - 1e-9)
    expect(out - prev).toBeLessThanOrEqual(1.25 * bps * 0.016 + 1e-9)
    prev = out
  }
  expect(Math.abs(out - t)).toBeLessThan(0.03)
  // a seek snaps
  ms += 16; expect(f.next(0, ms, bps)).toBe(0)
})
