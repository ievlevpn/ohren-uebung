import type { EnsembleId } from '../model'

/** Mirrors prep/fugue_prep/model.py (ENSEMBLE_INSTRUMENTS, CONTINUO, instruments_for, pan_for): keep in sync. */
export const ENSEMBLES: Record<EnsembleId, { name: string; instruments: string[] }> = {
  chamber: { name: 'Chamber', instruments: ['flute', 'violin', 'cello'] }, // cello = continuo
  harpsichord: { name: 'Harpsichord', instruments: ['harpsichord'] },
  strings: { name: 'Strings', instruments: ['violin', 'violin', 'viola', 'cello'] },
  organ: { name: 'Organ', instruments: ['organ'] },
}

/** Ensembles whose bass instrument is continuo: fewer voices than the table plays on the upper instruments only. */
const CONTINUO = new Set<string>(['chamber'])

/** Default instrument per voice (top first); exact port of Python `instruments_for`. */
export function instrumentsFor(ensemble: string, voices: number): string[] {
  const table = ENSEMBLES[ensemble as EnsembleId]?.instruments
  if (!table) throw new Error(`unknown ensemble '${ensemble}'`)
  if (voices === 1 || table.length === 1) return Array(voices).fill(table[0])
  if (CONTINUO.has(ensemble) && voices < table.length) return table.slice(0, voices)
  const upper = table.slice(0, -1), bass = table[table.length - 1]
  return [...Array.from({ length: voices - 1 }, (_, i) => upper[Math.min(i, upper.length - 1)]), bass]
}

/** Stereo position, -0.6 (top voice, left) to 0.6 (bass, right); exact port of Python `pan_for`. */
export function panFor(voice: number, voices: number): number {
  if (voices <= 1) return 0
  return Math.round((-0.6 + (1.2 * voice) / (voices - 1)) * 1e6) / 1e6
}

/** MIDI ranges per instrument; mirrors prep/fugue_prep/model.py INSTRUMENT_RANGES (keep in sync). */
export const INSTRUMENT_RANGES: Record<string, [number, number]> = {
  flute: [60, 96], violin: [55, 105], viola: [48, 88], cello: [36, 81], harpsichord: [29, 89], organ: [36, 96],
}

/** Semitones of `range` outside the instrument's compass (0: it fits). Unknown instruments always fit. */
function overflow(instrument: string, [lo, hi]: [number, number]): number {
  const r = INSTRUMENT_RANGES[instrument]
  return r ? Math.max(0, r[0] - lo) + Math.max(0, hi - r[1]) : 0
}

/**
 * The ensemble's instruments for these voices, each moved to another instrument of the same ensemble when its own
 * cannot reach the voice's notes (e.g. a tenor going below the viola plays the cello). A voice no instrument of the
 * ensemble fits keeps the one that leaves the fewest notes outside.
 */
export function instrumentsForRanges(ensemble: string, ranges: [number, number][]): string[] {
  const base = instrumentsFor(ensemble, ranges.length)
  const pool = [...new Set(ENSEMBLES[ensemble as EnsembleId]?.instruments ?? base)]
  return base.map((ins, v) => {
    const r = ranges[v]
    if (!r || overflow(ins, r) === 0) return ins
    let best = ins
    for (const alt of pool) if (overflow(alt, r) < overflow(best, r)) best = alt
    return best
  })
}
