import type { Library, PieceSummary } from './model'

/** Other names a listener may know a technique by. */
const ALIASES: Record<string, string> = {
  retrograde: 'crab cancrizans backwards',
  inversion: 'contrary motion mirror',
  'per tonos': 'rising spiral modulating',
  augmentation: 'slower',
  diminution: 'faster',
  canon: 'round',
}

/** Lower case, accents dropped, ♯/♭ spelled out, punctuation to spaces. */
export function normalise(s: string): string {
  return s.normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase()
    .replace(/♯/g, '#').replace(/♭/g, 'b').replace(/[^a-z0-9#]+/g, ' ').trim()
}

function haystack(lib: Library, p: PieceSummary): string[] {
  const coll = lib.collections.find(c => c.id === p.collection)
  const text = [
    p.title, p.catalogue, p.catalogue.replace(/\s+/g, ''), p.key, coll?.name ?? '', coll?.catalogue ?? '',
    ...p.techniques, ...p.techniques.map(t => ALIASES[t] ?? ''),
  ].join(' ')
  return normalise(text).split(' ')
}

/** 0: the title is the query ("sinfonia 9"); 1: the title starts with it ("sinf"); 2: the rest. */
function rank(p: PieceSummary, q: string): number {
  const title = normalise(p.title)
  if (title === q) return 0
  return title.startsWith(q) ? 1 : 2
}

/**
 * Pieces matching every word of the query. Words of one or two characters ("c", "15") must
 * match a whole word; longer words match the start of a word ("cancr", "847"). Pieces whose
 * title is the query come first, then titles that start with it, then the rest; library
 * order within each.
 */
export function search(lib: Library, query: string): PieceSummary[] {
  const q = normalise(query)
  const words = q.split(' ').filter(Boolean)
  if (words.length === 0) return []
  const found = lib.pieces.filter(p => {
    const hay = haystack(lib, p)
    return words.every(w => hay.some(h => (w.length <= 2 ? h === w : h.startsWith(w))))
  })
  return found.map((p, i) => ({ p, i, r: rank(p, q) }))
    .sort((a, b) => a.r - b.r || a.i - b.i).map(x => x.p)
}
