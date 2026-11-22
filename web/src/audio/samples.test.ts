import { expect, test } from 'vitest'
import type { Piece } from '../model'
import indexText from '../../public/samples/index.json?raw'

const index = JSON.parse(indexText) as Record<string, number[]>
const pieces = import.meta.glob('../../public/data/pieces/*.json', {
  eager: true, query: '?raw', import: 'default',
}) as Record<string, string>

test('every voice plays within 3 semitones of a sample of its own instrument', () => {
  expect(Object.keys(pieces).length).toBeGreaterThan(0)
  const far: string[] = []
  for (const text of Object.values(pieces)) {
    const p = JSON.parse(text) as Piece
    p.voices.forEach((v, i) => {
      const avail = index[v.instrument]
      expect(avail, `${p.id}: no samples for ${v.instrument}`).toBeDefined()
      for (const n of p.notes) {
        if (n.v !== i) continue
        const gap = Math.min(...avail.map(m => Math.abs(m - n.p)))
        if (gap > 3) far.push(`${p.id} voice ${i} (${v.instrument}) pitch ${n.p}`)
      }
    })
  }
  expect([...new Set(far)]).toEqual([])
})
