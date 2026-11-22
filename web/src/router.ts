/** Hash routes: `#/` shelf, `#/c/<collection>`, `#/i` glossary (`#/i/<entry>` opens at an entry), `#/r` recently heard, `#/p/<piece>`. */
export type Route =
  | { name: 'shelf' }
  | { name: 'index'; entry?: string }
  | { name: 'recent' }
  | { name: 'collection'; id: string }
  | { name: 'piece'; id: string }

export function parseRoute(hash: string): Route {
  const parts = hash.replace(/^#?\/?/, '').split('/').filter(Boolean).map(decodeURIComponent)
  if (parts.length === 1 && parts[0] === 'i') return { name: 'index' }
  if (parts.length === 2 && parts[0] === 'i') return { name: 'index', entry: parts[1] }
  if (parts.length === 1 && parts[0] === 'r') return { name: 'recent' }
  if (parts.length === 2 && parts[0] === 'c') return { name: 'collection', id: parts[1] }
  if (parts.length === 2 && parts[0] === 'p') return { name: 'piece', id: parts[1] }
  return { name: 'shelf' }
}

export function buildRoute(r: Route): string {
  switch (r.name) {
    case 'shelf': return '#/'
    case 'index': return r.entry ? `#/i/${encodeURIComponent(r.entry)}` : '#/i'
    case 'recent': return '#/r'
    case 'collection': return `#/c/${encodeURIComponent(r.id)}`
    case 'piece': return `#/p/${encodeURIComponent(r.id)}`
  }
}
