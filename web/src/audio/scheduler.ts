import type { Note } from '../model'

/**
 * Handle for one scheduled note. `release(at)`: end it at clock time `at`; if `at` is not after its start, it never sounds.
 * `retime(end)` (optional): move its end to clock time `end`, later or earlier (tempo change while it sounds).
 */
export interface NoteHandle { release(at: number): void; retime?(end: number): void }
/** Plays `note` at clock time `when` for `durationSec` seconds. */
export type PlayFn = (note: Note, when: number, durationSec: number) => NoteHandle | void

export const LOOKAHEAD = 0.2 // seconds
/** While the page is hidden (screen locked) timers may run late: schedule further ahead. */
export const BACKGROUND_LOOKAHEAD = 2

interface Scheduled { note: Note; handle: NoteHandle | void }

/**
 * Beat-based note scheduler. Time is the injected `clock` (seconds, e.g. AudioContext.currentTime);
 * position is in beats (tempo = beats per minute). Call `tick()` often (timer / rAF); it hands every note
 * starting within the next LOOKAHEAD seconds to `play` exactly once (a cursor over notes sorted by start).
 * A note belongs to the "past" iff note.s < current position; pause/tempo change cancel the scheduled-but-unstarted
 * notes (s >= position) and re-find the cursor at that position, so nothing is replayed or dropped.
 * `pause(heardBeat)` may stop at an earlier (heard) beat than the scheduled one: notes from there on are cut and
 * played again on resume. Starting mid-note re-strikes held notes for their remaining duration.
 */
export class Scheduler {
  private notes: Note[]
  private cursor = 0
  private playing = false
  private anchorBeat = 0
  private anchorTime = 0
  private active: Scheduled[] = []
  private muted: ReadonlySet<number> = new Set()
  private lookahead = LOOKAHEAD

  /** Seconds scheduled ahead of the clock (longer while the page is hidden). */
  setLookahead(sec: number): void { this.lookahead = sec }

  private clock: () => number
  private play: PlayFn
  private tempo: number

  constructor(clock: () => number, play: PlayFn, notes: Note[] = [], tempo = 60) {
    this.clock = clock
    this.play = play
    this.tempo = tempo
    this.notes = [...notes].sort((a, b) => a.s - b.s)
  }

  position(): number {
    return this.positionAt(this.clock())
  }

  /** The beat at clock time `t` (e.g. a smoothed reading of the clock, for drawing). */
  positionAt(t: number): number {
    return this.playing ? this.anchorBeat + ((t - this.anchorTime) * this.tempo) / 60 : this.anchorBeat
  }

  start(atBeat: number): void {
    if (this.playing) this.stopSounding()
    this.anchorBeat = atBeat
    this.anchorTime = this.clock()
    this.playing = true
    this.cursor = this.firstAtOrAfter(atBeat)
    // notes held across the start beat sound from here for what is left of them
    const spb = 60 / this.tempo
    for (const note of this.notes) {
      if (note.s >= atBeat) break
      if (note.s + note.d > atBeat && !this.muted.has(note.v)) this.active.push({ note, handle: this.play(note, this.anchorTime, (note.s + note.d - atBeat) * spb) })
    }
    this.tick()
  }

  /**
   * Stops the clock and releases sounding notes; pending ones are cancelled. `atBeat` (the heard position, at or
   * before the scheduled one) becomes the stopped position, so notes between it and the scheduled position replay on resume.
   */
  pause(atBeat?: number): void {
    if (!this.playing) return
    const pos = this.position()
    this.stopSounding()
    this.anchorBeat = atBeat === undefined ? pos : Math.min(pos, Math.max(0, atBeat))
    this.playing = false
  }

  /**
   * Voices that stay silent. Their notes are skipped from now on and the ones sounding now are released at once;
   * a voice taken out of the set plays again from its next note onset (held notes are not re-struck).
   */
  setMuted(voices: ReadonlySet<number>): void {
    this.muted = new Set(voices)
    const now = this.clock()
    this.active = this.active.filter((a) => {
      if (!this.muted.has(a.note.v)) return true
      a.handle?.release(now)
      return false
    })
  }

  setTempo(bpm: number): void {
    if (this.playing) {
      const pos = this.position()
      const now = this.clock()
      this.cancelPending(pos) // rescheduled under the new tempo
      // sounding notes keep their start but end where the new tempo puts them
      for (const a of this.active) a.handle?.retime?.(now + ((a.note.s + a.note.d - pos) * 60) / bpm)
      this.anchorBeat = pos
      this.anchorTime = now
      this.cursor = this.firstAtOrAfter(pos)
    }
    this.tempo = bpm
    if (this.playing) this.tick()
  }

  tick(): void {
    if (!this.playing) return
    const now = this.clock()
    const horizon = this.anchorBeat + ((now + this.lookahead - this.anchorTime) * this.tempo) / 60
    const spb = 60 / this.tempo
    while (this.cursor < this.notes.length && this.notes[this.cursor].s < horizon) {
      const note = this.notes[this.cursor++]
      if (this.muted.has(note.v)) continue // silent voice: the note is passed over, not played
      const when = this.anchorTime + (note.s - this.anchorBeat) * spb
      this.active.push({ note, handle: this.play(note, when, note.d * spb) })
    }
    // forget notes that finished (their handle can no longer matter)
    this.active = this.active.filter((a) => (a.note.s + a.note.d - this.anchorBeat) * spb + this.anchorTime > now)
  }

  private firstAtOrAfter(beat: number): number {
    let i = 0
    while (i < this.notes.length && this.notes[i].s < beat) i++
    return i
  }

  private cancelPending(pos: number): void {
    const now = this.clock()
    this.active = this.active.filter((a) => {
      if (a.note.s < pos) return true
      a.handle?.release(now)
      return false
    })
  }

  private stopSounding(): void {
    const now = this.clock()
    for (const a of this.active) a.handle?.release(now)
    this.active = []
  }
}
