import { readFileSync } from 'node:fs'
import { brotliDecompressSync } from 'node:zlib'
import { expect, test } from 'vitest'
import { NOTE_FOR_BEAT, tempoLabel } from './screens/tempo'
import { SERIF } from './render/textures'
import css from './styles.css?raw'

const fonts = Object.keys(import.meta.glob('./fonts/*.woff2'))

test('♯ ♭ ♮ ♩ ♪ and the half note come from a bundled engraved face, never a system fallback', () => {
  // EB Garamond has no accidentals; a subset of Garamond Libre (bundled) supplies them
  for (const style of ['Regular', 'Italic']) {
    const file = `./fonts/GaramondLibre-Accidentals-${style}.woff2`
    expect(fonts).toContain(file)
    expect(css).toContain(`url('${file}')`)
  }
  expect(css).toMatch(/unicode-range: U\+2669-266A, U\+266D-266F;/)
  expect(fonts).toContain('./fonts/NotoMusic-HalfNote.woff2')
  expect(css).toMatch(/unicode-range: U\+1D15E;/)
  expect(css).not.toMatch(/https?:\/\//) // nothing from the internet
  const stack = "'EB Garamond', 'Garamond Libre Accidentals', 'Noto Music Notes'"
  expect(css).toContain(`--serif: ${stack}`)
  expect(SERIF.startsWith(stack)).toBe(true)
})

// --- every glyph of a tempo label comes from a bundled face whose cmap has it ---


/** UIntBase128 (WOFF2): returns [value, next offset]. */
function base128(b: Uint8Array, at: number): [number, number] {
  let v = 0
  for (let i = 0; i < 5; i++) {
    const x = b[at + i]
    v = v * 128 + (x & 0x7f)
    if (!(x & 0x80)) return [v, at + i + 1]
  }
  throw new Error('bad UIntBase128')
}

/** The code points a WOFF2 font maps (its cmap: format 4 or 12 subtables). */
function woff2Cmap(file: Uint8Array): Set<number> {
  const dv = new DataView(file.buffer, file.byteOffset, file.byteLength)
  if (dv.getUint32(0) !== 0x774f4632) throw new Error('not WOFF2')
  const numTables = dv.getUint16(12)
  let at = 48
  const tables: { tag: number; len: number }[] = []
  for (let i = 0; i < numTables; i++) {
    const flags = file[at++]
    const tag = flags & 0x3f
    if (tag === 0x3f) at += 4 // an explicit tag: never cmap
    const version = flags >> 6
    let orig: number
    ;[orig, at] = base128(file, at)
    let len = orig
    const transformed = tag === 10 || tag === 11 ? version !== 3 : version !== 0
    if (transformed) [len, at] = base128(file, at)
    tables.push({ tag, len })
  }
  const data = brotliDecompressSync(file.subarray(at))
  let off = 0
  for (const t of tables) {
    if (t.tag === 0) return cmapCodes(new DataView(data.buffer, data.byteOffset + off, t.len))
    off += t.len
  }
  throw new Error('no cmap')
}

function cmapCodes(c: DataView): Set<number> {
  const out = new Set<number>()
  const n = c.getUint16(2)
  for (let i = 0; i < n; i++) {
    const sub = c.getUint32(4 + 8 * i + 4)
    const format = c.getUint16(sub)
    if (format === 12) {
      const groups = c.getUint32(sub + 12)
      for (let g = 0; g < groups; g++) {
        const s = c.getUint32(sub + 16 + 12 * g), e = c.getUint32(sub + 20 + 12 * g)
        const gid = c.getUint32(sub + 24 + 12 * g)
        for (let k = s; k <= e; k++) if (gid + (k - s)) out.add(k)
      }
    } else if (format === 4) {
      const seg = c.getUint16(sub + 6) / 2
      const ends = sub + 14, starts = ends + 2 * seg + 2, deltas = starts + 2 * seg, ros = deltas + 2 * seg
      for (let k = 0; k < seg; k++) {
        const e = c.getUint16(ends + 2 * k), s = c.getUint16(starts + 2 * k)
        const d = c.getUint16(deltas + 2 * k), ro = c.getUint16(ros + 2 * k)
        for (let ch = s; ch <= e && ch !== 0xffff; ch++) {
          const gid = ro === 0 ? (ch + d) & 0xffff
            : c.getUint16(ros + 2 * k + ro + 2 * (ch - s))
          if (gid) out.add(ch)
        }
      }
    }
  }
  return out
}

interface Face { family: string; style: string; file: string; ranges: [number, number][] | null }

function faces(): Face[] {
  return [...css.matchAll(/@font-face\s*{([^}]*)}/g)].map(([, body]) => {
    const get = (k: string) => body.match(new RegExp(`${k}:\\s*([^;]+);`))?.[1].trim()
    const range = get('unicode-range')
    return {
      family: get('font-family')!.replace(/'/g, ''),
      style: get('font-style') ?? 'normal',
      file: get('src')!.match(/url\('([^']+)'\)/)![1],
      ranges: range ? range.split(',').map(r => {
        const [a, b] = r.trim().replace('U+', '').split('-')
        return [parseInt(a, 16), parseInt(b ?? a, 16)] as [number, number]
      }) : null,
    }
  })
}

test('every glyph of a tempo label is in a bundled face’s cmap (never a system fallback)', () => {
  const stack = SERIF.split(',').map(f => f.trim().replace(/'/g, ''))
  const all = faces()
  const cmaps = new Map(all.map(f => [f.file, woff2Cmap(readFileSync(new URL(f.file, import.meta.url)))]))
  const labels = [...Object.keys(NOTE_FOR_BEAT).map(u => tempoLabel(72, Number(u))), tempoLabel(72)]
  expect(Object.values(NOTE_FOR_BEAT)).toContain('\u{1D15E}')
  for (const style of ['normal', 'italic']) {
    for (const label of labels) {
      for (const ch of label) {
        const cp = ch.codePointAt(0)!
        if (cp === 0x20) continue
        // the browser takes the first family in the stack with a face for this style whose
        // unicode-range covers the character and whose font has it
        const face = stack.map(fam => all.find(f => f.family === fam && f.style === style
          && (!f.ranges || f.ranges.some(([a, b]) => a <= cp && cp <= b))
          && cmaps.get(f.file)!.has(cp))).find(Boolean)
        expect(face, `${style} U+${cp.toString(16)} (${ch}) in "${label}"`).toBeTruthy()
      }
    }
  }
})
