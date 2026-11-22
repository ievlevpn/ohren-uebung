import { expect, test } from 'vitest'
import { exampleSounds } from './hear'
import { parseGlossary } from './model'
import glossaryText from '../../public/data/glossary.json?raw'

const glossary = parseGlossary(JSON.parse(glossaryText))
const canon = glossary.entries.find(e => e.id === 'canon')!.example!

test('▶ hear plays every note of the example at its tempo, on its voices\' instruments', () => {
  const sounds = exampleSounds(canon, 10)
  expect(sounds).toHaveLength(canon.notes.length)
  const spb = 60 / canon.tempo
  canon.notes.forEach((n, i) => {
    expect(sounds[i].when).toBeCloseTo(10 + n.s * spb)
    expect(sounds[i].dur).toBeCloseTo(n.d * spb)
    expect(sounds[i].instrument).toBe(canon.voices[n.v].instrument)
    expect(sounds[i].pan).toBe(canon.voices[n.v].pan)
  })
  expect(canon.tempo).toBeLessThanOrEqual(92) // slowly
})
