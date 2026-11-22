/** The piece's level while a glossary example plays over it (it keeps playing, quieter). */
export const DUCK = 0.3
/** Seconds to go down or back up: quick, without a click. */
export const DUCK_RAMP = 0.15

/** Ramps the piece's bus gain down to `DUCK` (on) or back to full (off), from where it is now. */
export function duck(gain: AudioParam, on: boolean, now: number): void {
  gain.cancelScheduledValues(now)
  gain.setValueAtTime(gain.value, now)
  gain.linearRampToValueAtTime(on ? DUCK : 1, now + DUCK_RAMP)
}
