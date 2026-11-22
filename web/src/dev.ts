// Dev page: renders the roll for one piece at one beat.
// /dev.html?piece=<id>&beat=<n>&w=<css px>&h=<css px>&markings=0
import { parsePiece } from './model'
import { layoutFor } from './render/layout'
import { drawRoll } from './render/roll'

async function main() {
  const q = new URLSearchParams(location.search)
  const id = q.get('piece') ?? 'frere-jacques'
  const beat = Number(q.get('beat') ?? 0)
  const w = Number(q.get('w') ?? innerWidth)
  const h = Number(q.get('h') ?? innerHeight)
  const markings = q.get('markings') !== '0'
  const piece = parsePiece(await (await fetch(`data/pieces/${id}.json`)).json())
  await document.fonts.load(`italic 13px 'EB Garamond'`)
  const dpr = devicePixelRatio || 1
  const canvas = document.querySelector<HTMLCanvasElement>('#roll')!
  canvas.width = Math.round(w * dpr)
  canvas.height = Math.round(h * dpr)
  canvas.style.width = `${w}px`
  canvas.style.height = `${h}px`
  const ctx = canvas.getContext('2d')!
  drawRoll(ctx, piece, layoutFor(piece, w, h, dpr), beat, { markings })
  document.body.dataset.ready = '1'
}
main()
