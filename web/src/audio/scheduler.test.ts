import { describe, expect, it } from 'vitest'
import type { Note } from '../model'
import { Scheduler, type PlayFn } from './scheduler'

// 4 bars of 4/4, one quarter note per beat, tempo 60 => 1 beat = 1 s.
const NOTES: Note[] = Array.from({ length: 16 }, (_, i) => ({ v: 0, p: 60 + (i % 5), s: i, d: 1 }))

function rig(tempo = 60, notes: Note[] = NOTES) {
  const t = { now: 100 }
  const played: { note: Note; when: number; dur: number; released?: number }[] = []
  const play: PlayFn = (note, when, dur) => {
    const rec: { note: Note; when: number; dur: number; released?: number } = { note, when, dur }
    played.push(rec)
    return { release: (at) => { rec.released = at } }
  }
  const s = new Scheduler(() => t.now, play, notes, tempo)
  const advance = (sec: number, step = 0.05) => {
    for (let x = 0; x < sec - 1e-9; x += step) { t.now += step; s.tick() }
  }
  return { t, played, s, advance }
}
const starts = (r: ReturnType<typeof rig>) => r.played.filter((x) => x.released === undefined || x.released > x.when).map((x) => x.note.s)

describe('Scheduler', () => {
  it('plays each note once', () => {
    const r = rig()
    r.s.start(0)
    r.advance(17)
    expect(r.played.map((x) => x.note.s)).toEqual(NOTES.map((n) => n.s))
    expect(new Set(r.played.map((x) => x.note)).size).toBe(16)
  })

  it('schedules at most 0.2 s ahead, at the right clock time', () => {
    const r = rig()
    r.s.start(0)
    r.s.tick() // horizon = 0.2 s: only the note at beat 0
    expect(r.played).toHaveLength(1)
    expect(r.played[0].when).toBeCloseTo(100, 9)
    expect(r.played[0].dur).toBeCloseTo(1, 9)
    r.advance(0.85) // now 100.85, horizon 101.05: beat 1 scheduled for 101
    expect(r.played.map((x) => x.when)).toEqual([100, 101])
  })

  it('does not replay notes that start before the start beat', () => {
    const r = rig()
    r.s.start(4)
    r.advance(2)
    expect(r.played[0].note.s).toBe(4)
    expect(r.played[0].when).toBeCloseTo(100, 9)
  })

  it('pauses and resumes without replaying notes', () => {
    const r = rig()
    r.s.start(0)
    r.advance(2.5) // pos 2.5; scheduled through beat 2 (horizon 2.7)
    r.s.pause()
    const pos = r.s.position()
    expect(pos).toBeCloseTo(2.5, 6)
    r.t.now += 10
    r.s.tick() // nothing while paused
    expect(r.s.position()).toBeCloseTo(2.5, 6)
    const resumedAt = r.t.now
    r.s.start(pos)
    r.advance(14)
    const full = r.played.filter((x) => Math.abs(x.dur - 1) < 1e-6 && !(x.released !== undefined && x.released <= x.when))
    expect(full.map((x) => x.note.s)).toEqual(NOTES.map((n) => n.s)) // every note struck in full exactly once, in order
    // the note held across the resume beat (beat 2, 2..3) is re-struck for its remaining half beat
    const restruck = r.played.filter((x) => x.dur < 0.99)
    expect(restruck.map((x) => [x.note.s, x.dur, x.when])).toEqual([[2, expect.closeTo(0.5, 6), resumedAt]])
  })

  it('pause at a heard position before the scheduled one: resume plays every note from the heard beat exactly once', () => {
    const r = rig()
    r.s.start(0)
    r.advance(3) // scheduled position 3, notes through beat 3 handed over (horizon 3.2)
    const heard = 2 // 1 s of output latency: the listener is at beat 2
    r.s.pause(heard)
    expect(r.s.position()).toBeCloseTo(2, 6)
    // notes 2 and 3 were handed to the output but never heard: both cut no later than now
    for (const x of r.played.filter((x) => x.note.s >= 2)) expect(x.released).toBeLessThanOrEqual(r.t.now + 1e-9)
    const before = r.played.length
    r.t.now += 5
    r.s.start(r.s.position())
    r.advance(15)
    const after = r.played.slice(before)
    expect(after.map((x) => x.note.s)).toEqual(NOTES.filter((n) => n.s >= heard).map((n) => n.s))
    expect(after.every((x) => x.dur === 1)).toBe(true)
  })

  it('a note held across the resume beat is re-struck with its remaining duration', () => {
    const long: Note[] = [{ v: 0, p: 60, s: 0, d: 8 }, { v: 1, p: 64, s: 3, d: 1 }]
    const r = rig(60, long)
    r.s.start(5.5)
    expect(r.played).toHaveLength(1)
    expect(r.played[0].note.s).toBe(0)
    expect(r.played[0].when).toBeCloseTo(100, 9)
    expect(r.played[0].dur).toBeCloseTo(2.5, 9) // 8 - 5.5 beats at 60 bpm
    r.advance(5)
    expect(r.played).toHaveLength(1) // the note at beat 3 is over; nothing else
  })

  it('tempo change retimes notes that are already sounding', () => {
    const t = { now: 100 }
    const ends: number[] = []
    const s = new Scheduler(() => t.now, () => ({ release() {}, retime: (end: number) => { ends.push(end) } }), [{ v: 0, p: 60, s: 0, d: 4 }], 60)
    s.start(0)
    t.now += 1; s.tick() // beat 1 of 4 sounding
    s.setTempo(120) // 3 beats left = 1.5 s
    expect(ends).toHaveLength(1)
    expect(ends[0]).toBeCloseTo(t.now + 1.5, 9)
  })

  it('cancels notes scheduled in the lookahead but not yet sounding when pausing, and releases sounding ones', () => {
    const r = rig()
    r.s.start(0)
    r.advance(0.9) // now 100.90, beat 1 scheduled for 101 (lookahead), beat 0 sounding
    expect(r.played.map((x) => x.note.s)).toEqual([0, 1])
    r.s.pause()
    const n0 = r.played[0], n1 = r.played[1]
    expect(n0.released).toBeCloseTo(100.9, 9) // sounding: released now
    expect(n1.released).toBeLessThanOrEqual(n1.when) // pending: cancelled
    r.s.start(r.s.position())
    r.advance(1)
    expect(r.played.filter((x) => x.note.s === 1 && !(x.released !== undefined && x.released <= x.when))).toHaveLength(1)
  })

  it('tempo change keeps position', () => {
    const r = rig()
    r.s.start(0)
    r.advance(2) // beat 2
    expect(r.s.position()).toBeCloseTo(2, 6)
    r.s.setTempo(120)
    expect(r.s.position()).toBeCloseTo(2, 6)
    r.advance(1) // 1 s at 120 bpm = 2 beats
    expect(r.s.position()).toBeCloseTo(4, 6)
    r.advance(8)
    expect(starts(r)).toEqual(NOTES.map((n) => n.s))
  })

  it('tempo change while paused takes effect on resume', () => {
    const r = rig()
    r.s.start(0)
    r.advance(1)
    r.s.pause()
    r.s.setTempo(30)
    expect(r.s.position()).toBeCloseTo(1, 6)
    r.s.start(r.s.position())
    r.advance(2)
    expect(r.s.position()).toBeCloseTo(2, 6) // 2 s at 30 bpm = 1 beat
  })

  it('position() is the start beat before playing and after pause', () => {
    const r = rig()
    expect(r.s.position()).toBe(0)
    r.s.start(3)
    expect(r.s.position()).toBe(3)
  })
})

describe('Scheduler muting', () => {
  // two voices, one note per beat each, 8 beats
  const TWO: Note[] = Array.from({ length: 16 }, (_, i) => ({ v: i % 2, p: 60 + (i % 2) * 7, s: Math.floor(i / 2), d: 2 }))

  it('does not start notes of a muted voice', () => {
    const r = rig(60, TWO)
    r.s.setMuted(new Set([1]))
    r.s.start(0)
    r.advance(9)
    expect(r.played.length).toBe(8)
    expect(r.played.every((x) => x.note.v === 0)).toBe(true)
  })

  it('releases the sounding notes of a voice muted mid-note, and only that voice', () => {
    const r = rig(60, TWO)
    r.s.start(0)
    r.advance(1.5) // notes of beats 0 and 1 sound (d = 2)
    const before = r.played.length
    r.s.setMuted(new Set([1]))
    const v1 = r.played.filter((x) => x.note.v === 1 && x.note.s <= 1)
    const v0 = r.played.filter((x) => x.note.v === 0)
    expect(v1.length).toBeGreaterThan(0)
    for (const x of v1) expect(x.released).toBeCloseTo(r.t.now, 9)
    for (const x of v0) expect(x.released).toBeUndefined()
    r.advance(2)
    expect(r.played.slice(before).every((x) => x.note.v === 0)).toBe(true)
  })

  it('plays an unmuted voice from its next onset, without re-striking held notes', () => {
    const r = rig(60, TWO)
    r.s.setMuted(new Set([1]))
    r.s.start(0)
    r.advance(2.5)
    r.s.setMuted(new Set())
    const n = r.played.length
    r.advance(3)
    const later = r.played.slice(n)
    expect(later.some((x) => x.note.v === 1)).toBe(true)
    expect(later.filter((x) => x.note.v === 1).every((x) => x.note.s > 2.5 - 0.2 && x.dur === 2)).toBe(true)
  })

  it('keeps the mute across pause, restart and tempo changes', () => {
    const r = rig(60, TWO)
    r.s.setMuted(new Set([1]))
    r.s.start(0)
    r.advance(2)
    r.s.setTempo(90)
    r.advance(1)
    r.s.pause()
    r.s.start(r.s.position()) // held notes are re-struck, muted ones not
    r.advance(8)
    expect(r.played.every((x) => x.note.v === 0)).toBe(true)
  })
})
