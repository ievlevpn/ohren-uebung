import { expect, test } from 'vitest'
import { barStart, dragBeat, loopRange, nextBarBeat, prevBarBeat } from './seek'

const plain = { beatsPerBar: 4, pickup: 0 }
const upbeat = { beatsPerBar: 4, pickup: 1 }

test('bars start where the time signature and upbeat put them', () => {
  expect(barStart(plain, 1)).toBe(0)
  expect(barStart(plain, 3)).toBe(8)
  expect(barStart(upbeat, 1)).toBe(1)
  expect(barStart(upbeat, 0)).toBe(0)
})

test('back goes to the bar start, or the bar before when already at its start', () => {
  expect(prevBarBeat(plain, 9.5)).toBe(8)
  expect(prevBarBeat(plain, 8.2)).toBe(4)
  expect(prevBarBeat(plain, 0.2)).toBe(0)
  expect(prevBarBeat(upbeat, 1.1)).toBe(0) // from bar 1 back to the upbeat
})

test('forward goes to the next bar, not past the end', () => {
  expect(nextBarBeat(plain, 0, 100)).toBe(4)
  expect(nextBarBeat(upbeat, 0, 100)).toBe(1)
  expect(nextBarBeat(plain, 98, 100)).toBe(100)
})

test('a loop covers whole bars, in either order', () => {
  expect(loopRange(plain, 9, 13, 100)).toEqual({ from: 8, to: 16, bars: [3, 4] })
  expect(loopRange(plain, 13, 9, 100)).toEqual({ from: 8, to: 16, bars: [3, 4] })
  expect(loopRange(plain, 9, 9, 100)).toEqual({ from: 8, to: 12, bars: [3, 3] })
  expect(loopRange(plain, 97, 99, 98)).toEqual({ from: 96, to: 98, bars: [25, 25] })
})

test('dragging right brings earlier music back; clamped to the piece', () => {
  expect(dragBeat(10, 50, 25, 100)).toBe(8)
  expect(dragBeat(10, -50, 25, 100)).toBe(12)
  expect(dragBeat(1, 500, 25, 100)).toBe(0)
  expect(dragBeat(99, -500, 25, 100)).toBe(100)
})
