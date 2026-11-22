import { expect, test } from 'vitest'
import type { Library } from './model'
import { search } from './search'
import libraryText from '../public/data/library.json?raw'

const library = JSON.parse(libraryText) as Library
const ids = (q: string) => search(library, q).map(p => p.id)

test('search finds by title, BWV number and key', () => {
  expect(ids('847')).toEqual(['bwv847'])
  expect(ids('BWV 847')).toEqual(['bwv847'])
  expect(ids('c minor').sort()).toEqual([
    'bwv1079-augmentationem', 'bwv1079-cancrizans', 'bwv1079-canone-perpetuo', 'bwv1079-fuga-canonica',
    'bwv1079-motum-contrarium', 'bwv1079-per-tonos', 'bwv1079-quaerendo', 'bwv1079-ricercar-a3',
    'bwv1079-ricercar-a6', 'bwv1079-thema-regium', 'bwv1079-violini-in-unisono', 'bwv847', 'invention02', 'sinfonia02',
  ])
  expect(ids('BWV 773')).toEqual(['invention02'])
  expect(ids('invention 1')[0]).toBe('invention01')
  expect(ids('BWV 795')).toEqual(['sinfonia09'])
  // the collection's name holds both words, so both books match; the piece named so comes first
  expect(ids('sinfonia 9')[0]).toBe('sinfonia09')
  expect(ids('invention 9')[0]).toBe('invention09')
  expect(ids('sinfonia 9')).toContain('invention09')
  expect(ids('sinf').slice(0, 15)).toEqual(Array.from({ length: 15 }, (_, i) => `sinfonia${String(i + 1).padStart(2, '0')}`))
  expect(ids('crab')).toEqual(['bwv1079-cancrizans'])
  expect(ids('cancrizans')).toEqual(['bwv1079-cancrizans'])
  expect(ids('frere')).toEqual(['frere-jacques'])           // accents do not matter
  expect(ids('variatio 15')).toEqual(['goldberg-var15'])
  expect(ids('1079')).toHaveLength(12)
  expect(ids('')).toEqual([])
  expect(ids('zzz')).toEqual([])
})
