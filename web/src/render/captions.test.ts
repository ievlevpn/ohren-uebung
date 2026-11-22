import { expect, test } from 'vitest'
import { captionAt } from './captions'

const caps = [
  { at: 0, text: 'one' },
  { at: 8, text: 'two' },
  { at: 16, text: 'three' },
]

test('captionAt picks the latest caption before the beat', () => {
  expect(captionAt(caps, 0)).toBe('one')
  expect(captionAt(caps, 7.99)).toBe('one')
  expect(captionAt(caps, 8)).toBe('two')
  expect(captionAt(caps, 100)).toBe('three')
  expect(captionAt([caps[2], caps[0], caps[1]], 9)).toBe('two')
})

test('captionAt is empty before the first caption', () => {
  expect(captionAt([{ at: 0.5, text: 'late' }], 0.25)).toBe('')
  expect(captionAt([], 3)).toBe('')
})
