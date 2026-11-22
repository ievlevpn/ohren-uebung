import { expect, test } from 'vitest'
import { loadRecent, noteHeard, pushRecent } from './recent'

test('recently heard keeps the last 8, newest first, without duplicates', () => {
  let list: string[] = []
  for (let i = 1; i <= 10; i++) list = pushRecent(list, `p${i}`)
  expect(list).toEqual(['p10', 'p9', 'p8', 'p7', 'p6', 'p5', 'p4', 'p3'])
  list = pushRecent(list, 'p5')
  expect(list).toEqual(['p5', 'p10', 'p9', 'p8', 'p7', 'p6', 'p4', 'p3'])
})

test('recently heard is kept in storage and survives bad data', () => {
  const store = new Map<string, string>()
  const storage = {
    getItem: (k: string) => store.get(k) ?? null,
    setItem: (k: string, v: string) => { store.set(k, v) },
  }
  expect(loadRecent(storage)).toEqual([])
  noteHeard('a', storage); noteHeard('b', storage); noteHeard('a', storage)
  expect(loadRecent(storage)).toEqual(['a', 'b'])
  store.set('listening-book:recent', '{not json')
  expect(loadRecent(storage)).toEqual([])
  store.set('listening-book:recent', '[1, "x", null]')
  expect(loadRecent(storage)).toEqual(['x'])
})
