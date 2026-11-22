/** How long a press must last before it becomes a hold (solo), and how far the finger may drift. */
export const HOLD_MS = 350
export const HOLD_SLOP = 10

/** The voices to silence: while `solo` is held, every voice but it; otherwise the listener's own muted set. */
export function heardMuted(muted: ReadonlySet<number>, solo: number | null, n: number): Set<number> {
  if (solo === null) return new Set(muted)
  const s = new Set<number>()
  for (let i = 0; i < n; i++) if (i !== solo) s.add(i)
  return s
}

/**
 * Press-and-hold on `el`: after HOLD_MS without moving, `onHold(v)` for the voice `pick` finds under the press;
 * on release `onRelease()`. The click that ends a hold is swallowed, so a short tap still toggles but a hold does not.
 */
export function pressAndHold(
  el: HTMLElement,
  pick: (e: PointerEvent) => number | null,
  onHold: (v: number) => void,
  onRelease: () => void,
): () => void {
  let timer = 0, held = false, swallow = false, x = 0, y = 0
  const cancel = () => { clearTimeout(timer); timer = 0 }
  const end = () => {
    cancel()
    if (held) { held = false; swallow = true; onRelease() }
  }
  const down = (e: PointerEvent) => {
    swallow = false
    if (e.button !== 0) return
    const v = pick(e)
    if (v === null) return
    x = e.clientX; y = e.clientY
    const id = e.pointerId
    cancel()
    timer = window.setTimeout(() => {
      timer = 0
      held = true
      try { el.setPointerCapture(id) } catch { /* pointer already gone */ }
      onHold(v)
    }, HOLD_MS)
  }
  const move = (e: PointerEvent) => {
    if (timer && Math.hypot(e.clientX - x, e.clientY - y) > HOLD_SLOP) cancel()
  }
  const click = (e: MouseEvent) => {
    if (!swallow) return
    swallow = false
    e.stopImmediatePropagation()
    e.preventDefault()
  }
  const menu = (e: Event) => { if (held || timer) e.preventDefault() } // long press must not open the touch menu
  el.addEventListener('pointerdown', down)
  el.addEventListener('pointermove', move)
  el.addEventListener('pointerup', end)
  el.addEventListener('pointercancel', end)
  el.addEventListener('click', click, true)
  el.addEventListener('contextmenu', menu)
  window.addEventListener('blur', end)
  return () => {
    end()
    el.removeEventListener('pointerdown', down)
    el.removeEventListener('pointermove', move)
    el.removeEventListener('pointerup', end)
    el.removeEventListener('pointercancel', end)
    el.removeEventListener('click', click, true)
    el.removeEventListener('contextmenu', menu)
    window.removeEventListener('blur', end)
  }
}
