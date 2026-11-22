import { afterEach, expect, test, vi } from 'vitest'
import { mountIndex } from './index'
import { parseGlossary } from '../glossary/model'
import glossaryText from '../../public/data/glossary.json?raw'

const glossary = parseGlossary(JSON.parse(glossaryText))

afterEach(() => { vi.unstubAllGlobals() })

/** Leaving the glossary (main.ts calls the screen's leave() before the next route renders)
 * stops its observers and its click handler. */
test('the glossary tears down its observer and listener when left', () => {
  const disconnect = vi.fn()
  vi.stubGlobal('ResizeObserver', class { observe() {} disconnect() { disconnect() } })
  vi.stubGlobal('document', { fonts: { load: () => Promise.resolve([]), ready: Promise.resolve() } })
  vi.stubGlobal('window', { scrollY: 0 })
  vi.stubGlobal('cancelAnimationFrame', () => {})
  const listeners = new Map<string, unknown>()
  const root = {
    querySelectorAll: () => [],
    querySelector: () => null,
    addEventListener: (k: string, f: unknown) => listeners.set(k, f),
    removeEventListener: (k: string, f: unknown) => { if (listeners.get(k) === f) listeners.delete(k) },
  } as unknown as HTMLElement
  const leave = mountIndex(root, glossary)
  expect(listeners.has('click')).toBe(true)
  leave()
  expect(listeners.has('click')).toBe(false)
  expect(disconnect).toHaveBeenCalled()
})
