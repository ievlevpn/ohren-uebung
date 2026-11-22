/** The note value shown for a beat of `beatUnit` quarter notes (fonts.test.ts checks the font covers each). */
export const NOTE_FOR_BEAT: Record<number, string> = { 0.5: '♪', 0.75: '♪.', 1: '♩', 1.5: '♩.', 2: '\u{1D15E}', 3: '\u{1D15E}.' }

/** "tempo ♩ = 72": the note value is the piece's beat (`beatUnit` quarter notes; default a quarter). */
export function tempoLabel(bpm: number, beatUnit = 1): string {
  return `tempo ${NOTE_FOR_BEAT[beatUnit] ?? '♩'} = ${bpm}`
}
