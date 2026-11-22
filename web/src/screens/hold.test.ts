import { expect, test } from 'vitest'
import { heardMuted } from './hold'

test('holding a voice silences every other voice, whatever the listener had muted', () => {
  expect([...heardMuted(new Set([1]), 1, 4)].sort()).toEqual([0, 2, 3])
  expect([...heardMuted(new Set(), 0, 3)].sort()).toEqual([1, 2])
})

test('without a hold the listener\'s own muted set applies, as a copy', () => {
  const muted = new Set([2])
  const out = heardMuted(muted, null, 4)
  expect([...out]).toEqual([2])
  out.add(0)
  expect(muted.has(0)).toBe(false)
})
