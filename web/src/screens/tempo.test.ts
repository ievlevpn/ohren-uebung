import { expect, test } from 'vitest'
import { tempoLabel } from './tempo'

test('the tempo names the beat note value', () => {
  expect(tempoLabel(132, 0.5)).toBe('tempo ♪ = 132')
  expect(tempoLabel(72, 1)).toBe('tempo ♩ = 72')
  expect(tempoLabel(72, undefined)).toBe('tempo ♩ = 72') // older data: quarter beats
  expect(tempoLabel(60, 1.5)).toBe('tempo ♩. = 60')
  expect(tempoLabel(64, 0.75)).toBe('tempo ♪. = 64') // 9/16: three dotted eighths a bar
  expect(tempoLabel(40, 2)).toBe('tempo \u{1D15E} = 40')
})
