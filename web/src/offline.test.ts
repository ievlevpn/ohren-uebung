import { expect, test } from 'vitest'
import { offlineUrls } from './offline'

test('offline list covers data, every piece and every sample', () => {
  const lib = { collections: [], techniques: [], pieces: [{ id: 'bwv847' }, { id: 'a b' }] } as never
  const urls = offlineUrls(lib, { harpsichord: [33, 36], flute: [60] })
  expect(urls).toContain('data/library.json')
  expect(urls).toContain('data/glossary.json')
  expect(urls).toContain('data/pieces/bwv847.json')
  expect(urls).toContain('data/pieces/a%20b.json')
  expect(urls).toContain('samples/harpsichord/36.mp3')
  expect(urls).toContain('samples/flute/60.mp3')
  expect(urls.length).toBe(2 + 2 + 1 + 3)
})
