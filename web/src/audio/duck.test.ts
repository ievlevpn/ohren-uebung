import { expect, test } from 'vitest'
import { DUCK, DUCK_RAMP, duck } from './duck'

function fakeParam(value: number) {
  const calls: [string, number, number?][] = []
  return {
    calls,
    value,
    cancelScheduledValues(t: number) { calls.push(['cancel', t]) },
    setValueAtTime(v: number, t: number) { calls.push(['set', v, t]) },
    linearRampToValueAtTime(v: number, t: number) { calls.push(['ramp', v, t]) },
  }
}

test('while an example sounds the piece is ducked to about 30 %, and restored after', () => {
  expect(DUCK).toBeCloseTo(0.3)
  const p = fakeParam(1)
  duck(p as unknown as AudioParam, true, 10)
  expect(p.calls).toEqual([['cancel', 10], ['set', 1, 10], ['ramp', DUCK, 10 + DUCK_RAMP]])
  const q = fakeParam(0.42) // half-way down: the restore starts from where it is
  duck(q as unknown as AudioParam, false, 11)
  expect(q.calls).toEqual([['cancel', 11], ['set', 0.42, 11], ['ramp', 1, 11 + DUCK_RAMP]])
  expect(DUCK_RAMP).toBeLessThanOrEqual(0.25) // quick, but no click
})
