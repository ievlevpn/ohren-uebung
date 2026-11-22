import { expect, test } from 'vitest'
import { buildRoute, parseRoute, type Route } from './router'

test('routes parse and build', () => {
  expect(parseRoute('')).toEqual({ name: 'shelf' })
  expect(parseRoute('#/')).toEqual({ name: 'shelf' })
  expect(parseRoute('#/c/musical-offering')).toEqual({ name: 'collection', id: 'musical-offering' })
  expect(parseRoute('#/i')).toEqual({ name: 'index' })
  expect(parseRoute('#/i/inversion')).toEqual({ name: 'index', entry: 'inversion' })
  expect(parseRoute('#/r')).toEqual({ name: 'recent' })
  expect(parseRoute('#/p/bwv1079-cancrizans')).toEqual({ name: 'piece', id: 'bwv1079-cancrizans' })
  expect(parseRoute('#/nowhere/at/all')).toEqual({ name: 'shelf' })
  expect(parseRoute('#/p/')).toEqual({ name: 'shelf' })
  const all: Route[] = [
    { name: 'shelf' }, { name: 'index' }, { name: 'index', entry: 'per-tonos' }, { name: 'recent' },
    { name: 'collection', id: 'wtc' }, { name: 'piece', id: 'goldberg-var15' },
  ]
  for (const r of all) expect(parseRoute(buildRoute(r))).toEqual(r)
  expect(buildRoute({ name: 'piece', id: 'bwv847' })).toBe('#/p/bwv847')
  expect(buildRoute({ name: 'shelf' })).toBe('#/')
})
