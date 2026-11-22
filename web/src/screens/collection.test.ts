import { expect, test } from 'vitest'
import type { Library } from '../model'
import { renderCollection } from './collection'
import { positionLabel } from './common'
import libraryText from '../../public/data/library.json?raw'

const library = JSON.parse(libraryText) as Library

test('each book of a collection numbers its pieces from 1', () => {
  const app = { innerHTML: '' } as HTMLElement
  renderCollection(app, library, 'inventions')
  expect(app.innerHTML).toContain('1 · Invention 1<')
  expect(app.innerHTML).toContain('1 · Sinfonia 1<')
  expect(app.innerHTML).toContain('15 · Sinfonia 15<')
  expect(app.innerHTML).not.toContain('16 · ')
})

test('a piece header places the piece in its book when the collection has several', () => {
  expect(positionLabel(library, 'sinfonia15')).toBe('VI · Sinfonias · 15 of 15')
  expect(positionLabel(library, 'invention02')).toBe('VI · Inventions · 2 of 15')
  expect(positionLabel(library, 'bwv847')).toBe('V · Book I · Fugue 2') // its own number
  expect(positionLabel(library, 'bwv853')).toBe('V · Book I · Fugue 8')
  expect(positionLabel(library, 'goldberg-var06')).toBe('III · 2 of 9')
})

test('WTC fugues carry their own fugue number, not their place in the list', () => {
  const app = { innerHTML: '' } as HTMLElement
  renderCollection(app, library, 'wtc')
  expect(app.innerHTML).toContain('3 · Fugue in C♯ major<')
  expect(app.innerHTML).toContain('5 · Fugue in D major<')
  expect(app.innerHTML).toContain('12 · Fugue in F minor<')
  expect(app.innerHTML).not.toContain('4 · Fugue in D major<')
})

test('next/previous walk the collection in order, across its books, and stop at its ends', async () => {
  const { neighbours } = await import('./common')
  expect(neighbours(library, 'invention15')).toEqual({ prev: 'invention14', next: 'sinfonia01' })
  const first = library.collections.find(c => c.id === 'wtc')!.books[0].pieces[0]
  expect(neighbours(library, first).prev).toBeUndefined()
  expect(neighbours(library, 'nope')).toEqual({})
})
