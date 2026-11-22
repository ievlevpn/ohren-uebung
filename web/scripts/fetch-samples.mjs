// Downloads FluidR3_GM MP3 samples (via gleitz/midi-js-soundfonts) into public/samples/<instrument>/<midi>.mp3,
// every third semitone (C, Eb, Gb, A in each octave) across the range the 11 pieces need under any ensemble.
// Writes public/samples/index.json and LICENSE.txt. Run: node scripts/fetch-samples.mjs
import { mkdir, writeFile } from 'node:fs/promises'
import { existsSync } from 'node:fs'

const BASE = 'https://raw.githubusercontent.com/gleitz/midi-js-soundfonts/gh-pages'
const GM = { harpsichord: 'harpsichord', organ: 'church_organ', flute: 'flute', violin: 'violin', viola: 'viola', cello: 'cello' }
// MIDI range per instrument: covers every piece's own instruments (voice.instrument in web/public/data/pieces,
// checked by src/audio/samples.test.ts). Under another ensemble chosen in the player a voice may lie further
// from its nearest sample (the sampler pitch-shifts it).
const RANGE = { cello: [33, 77], violin: [48, 86], flute: [54, 86], harpsichord: [33, 86], organ: [33, 86], viola: [48, 79] }
const NAMES = ['C', 'Db', 'D', 'Eb', 'E', 'F', 'Gb', 'G', 'Ab', 'A', 'Bb', 'B']
const noteName = (m) => `${NAMES[m % 12]}${Math.floor(m / 12) - 1}`

const out = new URL('../public/samples/', import.meta.url).pathname
const index = {}
for (const [inst, [lo, hi]] of Object.entries(RANGE)) {
  // available midis: pitch classes 0,3,6,9; cover [lo, hi] with a sample at or below lo and at or above hi
  const first = lo - (((lo % 3) + 3) % 3), last = hi + ((3 - (hi % 3)) % 3)
  const midis = []
  for (let m = first; m <= last; m += 3) midis.push(m)
  index[inst] = midis
  await mkdir(`${out}${inst}`, { recursive: true })
  for (const m of midis) {
    const file = `${out}${inst}/${m}.mp3`
    if (existsSync(file)) continue
    const url = `${BASE}/FluidR3_GM/${GM[inst]}-mp3/${noteName(m)}.mp3`
    const r = await fetch(url)
    if (!r.ok) throw new Error(`${url}: ${r.status}`)
    await writeFile(file, Buffer.from(await r.arrayBuffer()))
    console.log(inst, m, noteName(m))
  }
}
await writeFile(`${out}index.json`, JSON.stringify(index) + '\n')
const lic = await (await fetch(`${BASE}/LICENSE.txt`)).text()
await writeFile(`${out}LICENSE.txt`, `Samples: FluidR3_GM soundfont, pre-rendered to MP3 by gleitz/midi-js-soundfonts
(https://github.com/gleitz/midi-js-soundfonts). The repository's README states the FluidR3_GM samples are
released under the Creative Commons Attribution 3.0 license (https://creativecommons.org/licenses/by/3.0/us/):
free to share and adapt, including privately and commercially, provided attribution is given.
Attribution: FluidR3_GM by Frank Wen; MP3 renders by Benjamin Gleitzman (midi-js-soundfonts).

The midi-js-soundfonts repository itself (code and packaging) is under this licence:

${lic}`)
