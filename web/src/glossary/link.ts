import type { Mark, Piece } from '../model'
import { esc } from '../screens/common'
import type { Glossary } from './model'

/** A technique word in a text: [start, end) and the glossary entry it opens. */
export interface TermHit { start: number; end: number; entry: string }

/*
 * The same rules as the data guard, prep/tests/test_glossary.py `unsafe_uses`: an alias is
 * an ordinary word after a modal, "to" or a pronoun subject ("will answer", "it comes"),
 * or, for the aliases that are also verbs, before a particle or object ("comes back",
 * "answers them"). The guard keeps such uses out of the data; the linker skips them too.
 */
const BEFORE = /\b(will|to|can|could|may|might|must|shall|should|would|it|he|she|they|which|that|who)\s+$/i
const AFTER: Record<string, RegExp> = {
  comes: /^\s+(back|in|round|out|up|down|along|from|to|again)\b/i,
  answer: /^\s+(it|them|him|her|back|again)\b/i,
  mirror: /^\s+(it|them|the|each)\b/i,
}
/**
 * "answer" is linked only as a noun: after an article, a possessive or an ordinal ("the answer",
 * "its answer", "the subject's answer", "a tonal answer"), or opening the text ("☞ Answer:", a
 * label). After a subject it is the verb ("the lower voice answers"), never linked.
 */
const NOUN_ONLY: Record<string, RegExp> = {
  answer: /(?:^[\s☞]*|\b(?:the|an|a|its|this|that|each|every|first|second|third|fourth|next|last|tonal|real|one|no)\s+|['’]s\s+)$/i,
}
/** In a fugue (a piece that is not a canon) dux and comes are names for subject and answer. */
const FUGUE_NAMES: Record<string, string> = { dux: 'subject', comes: 'answer', 'dux and comes': 'subject' }

/** True if the piece is a canon (its techniques include the canon entry). */
export function isCanon(piece: Pick<Piece, 'techniques'>, g: Glossary): boolean {
  return piece.techniques.some(t => g.techniques[t] === 'canon')
}

/** A word character as Python's `\w` (letters and digits of any script, `_`), plus the hyphen. */
const WORD = '[\\p{L}\\p{N}_-]'
const reEscape = (s: string) => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')

interface Alias { alias: string; entry: string; re: RegExp }
const aliasCache = new WeakMap<Glossary, Alias[]>()
/** Every linkable alias, longest first (so "canon at the fourth" beats "canon"). */
function aliases(g: Glossary): Alias[] {
  let out = aliasCache.get(g)
  if (!out) {
    out = g.entries.flatMap(e => e.links.map(alias => ({
      alias, entry: e.id,
      // whole words only, the alias or its plural / 3rd person (+s)
      re: new RegExp(`(?<!${WORD})${reEscape(alias)}s?(?!${WORD})`, 'giu'),
    }))).sort((a, b) => b.alias.length - a.alias.length)
    aliasCache.set(g, out)
  }
  return out
}

/** Spans of the glossary's `ordinary` phrases ("will answer it") in `text`, any case. */
function ordinarySpans(text: string, g: Glossary): [number, number][] {
  const low = text.toLowerCase()
  const out: [number, number][] = []
  for (const p of g.ordinary) {
    const q = p.toLowerCase()
    for (let i = low.indexOf(q); i >= 0; i = low.indexOf(q, i + 1)) out.push([i, i + q.length])
  }
  return out
}

/**
 * Every technique word in `text`, in order (`piece`: the piece it belongs to; in a fugue
 * "dux" and "comes" open Subject and Answer, in a canon Canon): each whole-word occurrence of a linkable alias
 * (`links`, never the other aliases) that is not inside an `ordinary` phrase and not used
 * as an ordinary verb. Overlaps go to the longer alias.
 */
export function findTerms(text: string, g: Glossary, piece?: Pick<Piece, 'techniques'>): TermHit[] {
  const skip = ordinarySpans(text, g)
  const fugue = piece !== undefined && !isCanon(piece, g)
  const hits: TermHit[] = []
  for (const { alias, entry, re } of aliases(g)) {
    re.lastIndex = 0
    for (let m = re.exec(text); m; m = re.exec(text)) {
      const start = m.index, end = start + m[0].length
      if (skip.some(([lo, hi]) => start < hi && lo < end)) continue
      if (hits.some(h => start < h.end && h.start < end)) continue
      if (BEFORE.test(text.slice(0, start)) || AFTER[alias]?.test(text.slice(end))) continue
      if (NOUN_ONLY[alias] && !NOUN_ONLY[alias].test(text.slice(0, start))) continue
      hits.push({ start, end, entry: (fugue && FUGUE_NAMES[alias]) || entry })
    }
  }
  return hits.sort((a, b) => a.start - b.start)
}

/**
 * `text` as HTML, its technique words tappable: the first use of each entry becomes a button
 * (a caption that says "motive" three times links it once).
 */
export function linkHtml(text: string, g: Glossary, piece?: Pick<Piece, 'techniques'>): string {
  const seen = new Set<string>()
  let out = '', at = 0
  for (const h of findTerms(text, g, piece)) {
    if (seen.has(h.entry)) continue
    seen.add(h.entry)
    const word = text.slice(h.start, h.end)
    out += esc(text.slice(at, h.start)) +
      `<button type="button" class="term" data-entry="${esc(h.entry)}" data-term="${esc(word)}">${esc(word)}</button>`
    at = h.end
  }
  return out + esc(text.slice(at))
}

/** The transforms of an entry label ("subject inverted diminished"; prep/fugue_prep/fugue.py TRANSFORMS). */
const TRANSFORMS: Record<string, string> = { inverted: 'inversion', augmented: 'augmentation', diminished: 'diminution' }

/** Augmentation if the follower's notes in a stretch mark are longer than the leader's, else diminution. */
function stretchEntry(piece: Piece, m: Mark): string {
  let lead = 0, follow = 0
  for (const t of piece.threads) {
    const a = piece.notes[t.a], b = piece.notes[t.b]
    if ((m.voice != null && b.v !== m.voice) || b.s < m.start || b.s > m.end) continue
    lead += a.d; follow += b.d
  }
  return follow >= lead ? 'augmentation' : 'diminution'
}

/**
 * The entries a label drawn on the roll opens, in reading order. `mark` is the mark it
 * belongs to (for the rail's pointer, the opening entry); `text` is the lettering drawn.
 */
export function labelEntries(mark: Mark | null, text: string, piece: Piece, g: Glossary): string[] {
  const known = (ids: string[]) => ids.filter((id, i) => ids.indexOf(id) === i && g.entries.some(e => e.id === id))
  switch (mark?.kind) {
    case 'mirror-axis': return known(['inversion'])
    case 'crab-axis': return known(['retrograde'])
    case 'rise': return known(['per-tonos'])
    case 'stretto': return known(['stretto'])
    case 'stretch': return known([stretchEntry(piece, mark)])
    case 'entry': {
      const label = mark.label ?? text
      const words = [...label.matchAll(/[\p{L}]+/gu)]
      const found = [
        ...findTerms(label, g, piece).map(h => ({ at: h.start, id: h.entry })),
        ...words.flatMap(w => TRANSFORMS[w[0]] ? [{ at: w.index!, id: TRANSFORMS[w[0]] }] : []),
        // "subject II": an entry of a fugue on several subjects also opens that card
        ...words.flatMap(w => /^(I{1,3}|IV)$/.test(w[0]) ? [{ at: w.index!, id: 'double-fugue' }] : []),
      ].sort((a, b) => a.at - b.at)
      return known(found.map(f => f.id))
    }
    default: return known(findTerms(text, g, piece).map(h => h.entry))
  }
}
