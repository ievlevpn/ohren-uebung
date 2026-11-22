import { expect, test } from 'vitest'
import { parsePiece } from './model'
import fixtureText from '../../prep/tests/fixtures/tiny_piece.json?raw'

const fixture = JSON.parse(fixtureText)

test('parsePiece accepts the fixture', () => {
  const piece = parsePiece(fixture)
  expect(piece.id).toBe('tiny')
  expect(piece.notes).toHaveLength(8)
  expect(piece.voices).toHaveLength(2)
})

test('parsePiece rejects a piece without voices', () => {
  const { voices: _voices, ...rest } = fixture
  expect(() => parsePiece(rest)).toThrow(/voices/)
})
