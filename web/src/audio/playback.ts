/**
 * Sample loads can overlap (the listener switches ensemble A → B → C quickly). Each load takes a token;
 * only the latest token may end the loading state, so an older load finishing late never enables Play
 * for instruments that are not loaded yet.
 */
export class LoadGate {
  private gen = 0
  private pending = false
  private error = false

  get loading(): boolean { return this.pending }
  get failed(): boolean { return this.error }

  begin(): number {
    this.pending = true
    this.error = false
    return ++this.gen
  }

  /** True if `token` is the latest load (the caller may enable Play and resume). */
  finish(token: number): boolean {
    if (token !== this.gen || !this.pending) return false
    this.pending = false
    return true
  }

  /** True if `token` is the latest load (the caller should show the failure). */
  fail(token: number): boolean {
    if (token !== this.gen || !this.pending) return false
    this.pending = false
    this.error = true
    return true
  }
}

/** The beat being heard now: the scheduled position minus the output latency, never before the start. */
export function heardPosition(position: number, latencySec: number, bpm: number): number {
  const lag = Number.isFinite(latencySec) && latencySec > 0 ? (latencySec * bpm) / 60 : 0
  return Math.max(0, position - lag)
}

/**
 * A smooth reading of a coarse clock, for drawing. Android Chrome advances AudioContext.currentTime in steps of
 * one audio buffer (tens of ms), so a roll drawn from it moves in jumps. Between steps this extrapolates with the
 * wall clock; it never runs more than `maxAhead` s past the audio clock and never goes backwards.
 */
export function smoothClock(audioNow: () => number, wallMs: () => number, maxAhead = 0.12): () => number {
  let base = NaN, baseWall = 0, last = -Infinity
  return () => {
    const a = audioNow(), w = wallMs()
    if (a !== base) { base = a; baseWall = w }
    const est = Math.min(base + (w - baseWall) / 1000, base + maxAhead)
    if (est < last && last - est < maxAhead) return last // a step that lands just behind the estimate: hold still
    last = est
    return est
  }
}

/** Errors larger than this (beats) are taken at once: a seek, a resume, a clock that was far off. */
export const SNAP_BEATS = 0.75
/** Share of the remaining error corrected per 60 Hz frame. */
const CORRECTION = 0.12
/** The drawn speed stays within this share of the music's speed while it catches up. */
const MAX_EASE = 0.25

/**
 * The beat the roll is drawn at, smoothed. `target` is where the music is heard (it may stall, step, or move back a
 * little when the browser revises its output latency, especially in the first moments of playback). The drawn beat
 * moves at the music's speed once the target is moving, eases toward the target, never steps backwards, and snaps
 * on large jumps. Call once per frame; `reset()` on start and seek.
 */
export function positionFilter() {
  let shown = NaN, lastMs = 0, lastTarget = NaN, moving = false
  return {
    reset() { shown = NaN; moving = false },
    next(target: number, nowMs: number, beatsPerSec: number): number {
      if (!Number.isFinite(shown) || Math.abs(target - shown) > SNAP_BEATS) {
        shown = target; lastMs = nowMs; lastTarget = target; moving = false
        return shown
      }
      const dt = Math.min(0.1, Math.max(0, (nowMs - lastMs) / 1000))
      lastMs = nowMs
      if (target > lastTarget) moving = true // the clock has started: from now on advance at the music's speed
      lastTarget = target
      const step = moving ? beatsPerSec * dt : 0
      const k = 1 - (1 - CORRECTION) ** (dt * 60)
      // catch up by easing the speed, never more than ±MAX_EASE of the music's own
      const fix = Math.max(-MAX_EASE * step, Math.min(MAX_EASE * step, (target - shown - step) * k))
      shown = Math.max(shown, shown + step + fix)
      return shown
    },
  }
}
