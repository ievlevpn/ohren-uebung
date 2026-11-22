import { parseGlossary, type Glossary } from './glossary/model'
import { parsePiece, type Library, type Piece } from './model'

// Paths are relative to the page, so the site works from any subpath.
let library: Promise<Library> | null = null
let glossary: Promise<Glossary> | null = null
const pieces = new Map<string, Promise<Piece>>()

async function getJson(url: string): Promise<unknown> {
  const r = await fetch(url)
  if (!r.ok) throw new Error(`${url}: HTTP ${r.status}`)
  return r.json()
}

export function loadLibrary(): Promise<Library> {
  library ??= getJson('data/library.json').then(j => j as Library)
  library.catch(() => { library = null })
  return library
}

export function loadPiece(id: string): Promise<Piece> {
  let p = pieces.get(id)
  if (!p) {
    p = getJson(`data/pieces/${encodeURIComponent(id)}.json`).then(parsePiece)
    p.catch(() => pieces.delete(id))
    pieces.set(id, p)
  }
  return p
}

export function loadGlossary(): Promise<Glossary> {
  glossary ??= getJson('data/glossary.json').then(parseGlossary)
  glossary.catch(() => { glossary = null })
  return glossary
}
