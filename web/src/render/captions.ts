import type { Caption } from '../model'

/** The caption in force at `beat`: the latest one starting at or before it ('' before the first). */
export function captionAt(captions: Caption[], beat: number): string {
  let best: Caption | null = null
  for (const c of captions) if (c.at <= beat && (best === null || c.at >= best.at)) best = c
  return best === null ? '' : best.text
}
