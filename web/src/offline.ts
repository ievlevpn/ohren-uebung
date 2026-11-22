import type { Library } from './model'

/** Every file the app needs to play everything: data, the glossary, all pieces, and all instrument samples. */
export function offlineUrls(lib: Library, samples: Record<string, number[]>): string[] {
  return [
    'data/library.json', 'data/glossary.json',
    ...lib.pieces.map(p => `data/pieces/${encodeURIComponent(p.id)}.json`),
    'samples/index.json',
    ...Object.entries(samples).flatMap(([ins, ms]) => ms.map(m => `samples/${ins}/${m}.mp3`)),
  ]
}

/**
 * Fetches every file once so the service worker keeps it (offline use). Four at a time; `progress(done, total)`
 * after each. Resolves with the number that failed.
 */
export async function keepOffline(lib: Library, progress: (done: number, total: number) => void): Promise<number> {
  const samples = (await (await fetch('samples/index.json')).json()) as Record<string, number[]>
  const urls = offlineUrls(lib, samples)
  let done = 0, failed = 0, next = 0
  const worker = async () => {
    while (next < urls.length) {
      const u = urls[next++]
      try { const r = await fetch(u); if (!r.ok) failed++; else await r.arrayBuffer() } catch { failed++ }
      progress(++done, urls.length)
    }
  }
  await Promise.all([worker(), worker(), worker(), worker()])
  return failed
}
