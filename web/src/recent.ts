/** Pieces opened in the player, newest first, kept in localStorage. */
export const RECENT_MAX = 8
const KEY = 'listening-book:recent'

export interface StorageLike { getItem(k: string): string | null; setItem(k: string, v: string): void }

export function pushRecent(list: string[], id: string, max = RECENT_MAX): string[] {
  return [id, ...list.filter(x => x !== id)].slice(0, max)
}

function defaultStorage(): StorageLike | null {
  try { return globalThis.localStorage ?? null } catch { return null }
}

export function loadRecent(storage: StorageLike | null = defaultStorage()): string[] {
  if (!storage) return []
  try {
    const v: unknown = JSON.parse(storage.getItem(KEY) ?? '[]')
    return Array.isArray(v) ? v.filter((x): x is string => typeof x === 'string').slice(0, RECENT_MAX) : []
  } catch { return [] }
}

export function noteHeard(id: string, storage: StorageLike | null = defaultStorage()): void {
  if (!storage) return
  try { storage.setItem(KEY, JSON.stringify(pushRecent(loadRecent(storage), id))) } catch { /* private mode: ignore */ }
}
