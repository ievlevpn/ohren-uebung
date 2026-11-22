import type { Piece } from '../model'

/** An illustration: a tiny piece drawn by the roll's renderer, with its caption. */
export type Example = Piece & { caption: string }
export interface GlossaryEntry {
  id: string; title: string
  /** Shown small beside the title ("also: contrary motion · per motum contrarium"; may be empty). */
  also: string
  /** Lower-case names that open this entry; every library technique is one of them. */
  aliases: string[]
  /** The aliases a caption may link: not those that are also ordinary words ("round", "cadence"). */
  links: string[]
  /** One sentence, for cards. */
  short: string
  /** The definition, 2–4 sentences. */
  text: string
  related: string[]
  /** Pieces carrying the technique (generated from library.json), with an optional word ("at the fourth"). */
  pieces: { id: string; note?: string }[]
  example?: Example
}
export interface Glossary {
  entries: GlossaryEntry[]
  /** Library technique -> entry id. */
  techniques: Record<string, string>
  /** Phrases in which a linkable alias is an ordinary word ("will answer it"): never linked. */
  ordinary: string[]
}

/** Checks the shape of glossary.json and throws on a missing or mistyped field. */
export function parseGlossary(json: unknown): Glossary {
  const o = json as Partial<Glossary> | null
  if (!o || !Array.isArray(o.entries) || typeof o.techniques !== 'object' || !Array.isArray(o.ordinary)) throw new Error('glossary: bad shape')
  for (const e of o.entries) {
    for (const k of ['id', 'title', 'also', 'short', 'text'] as const) {
      if (typeof e[k] !== 'string') throw new Error(`glossary: entry ${e.id ?? '?'} lacks '${k}'`)
    }
    for (const k of ['aliases', 'links', 'related', 'pieces'] as const) {
      if (!Array.isArray(e[k])) throw new Error(`glossary: entry ${e.id} lacks '${k}'`)
    }
    if (e.example && (!Array.isArray(e.example.notes) || !Array.isArray(e.example.voices))) {
      throw new Error(`glossary: entry ${e.id} has a bad example`)
    }
  }
  return o as Glossary
}

/** The entry a technique name (or any alias, any case) belongs to. */
export function entryFor(g: Glossary, name: string): GlossaryEntry | undefined {
  const n = name.trim().toLowerCase()
  return g.entries.find(e => e.aliases.includes(n))
}

/** The last beat of an example. */
export function exampleEnd(ex: Piece): number {
  return ex.notes.reduce((m, n) => Math.max(m, n.s + n.d), 0)
}
