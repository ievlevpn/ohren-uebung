import { getAudio } from '../audio/context'
import { ENSEMBLES, instrumentsForRanges } from '../audio/ensembles'
import { duck } from '../audio/duck'
import { LoadGate, heardPosition, positionFilter, smoothClock } from '../audio/playback'
import { BACKGROUND_LOOKAHEAD, LOOKAHEAD, Scheduler, type PlayFn } from '../audio/scheduler'
import { loadGlossary, loadPiece } from '../data'
import { createCard } from '../glossary/card'
import { labelEntries, linkHtml } from '../glossary/link'
import type { Glossary } from '../glossary/model'
import { barOf, type EnsembleId, type Library, type Piece } from '../model'
import { noteHeard } from '../recent'
import { captionAt } from '../render/captions'
import { FRAME_MS, canvasDpr, layoutFor, type Layout } from '../render/layout'
import { drawRoll, voiceAt } from '../render/roll'
import { labelAt, type LabelHit } from '../render/techniques'
import { collectionHref, collectionOf, esc, neighbours, positionLabel, summary } from './common'
import { heardMuted, pressAndHold } from './hold'
import { barStart, dragBeat, loopRange, nextBarBeat, prevBarBeat } from './seek'
import { tempoLabel } from './tempo'
import { INK } from '../render/textures'
import { DEFAULT_TUNING, FINAL_HOLD, TUNINGS, accent, envelopeFor, makeRoom, roomLevel, tuningById, tuningFactor } from '../audio/shape'

export const TEMPO_STEP = 4
export const TEMPO_MIN = 40
export const TEMPO_MAX = 120

/** Next tempo after a ± step; the range always includes the piece's own tempo. */
export function stepTempo(bpm: number, dir: 1 | -1, own: number): number {
  const lo = Math.min(TEMPO_MIN, own), hi = Math.max(TEMPO_MAX, own)
  return Math.min(hi, Math.max(lo, bpm + dir * TEMPO_STEP))
}

/** Debug counters, exposed on window in dev builds only. */
interface Debug { scheduled: number; byVoice: number[]; failed: number; state(): string; position(): number }
declare global { interface Window { __listening?: Debug } }

/** The player for one piece. Returns a function that stops everything when the page is left. */
export async function renderPlayer(app: HTMLElement, lib: Library, id: string, alive: () => boolean): Promise<() => void> {
  let piece: Piece
  // without the glossary the player still plays; its technique words are just not tappable
  const glossary: Promise<Glossary | null> = loadGlossary().catch((e) => { console.error(e); return null })
  try { piece = await loadPiece(id) } catch (e) {
    if (alive()) app.innerHTML = `<main class="sheet"><p class="empty">Could not open this piece (${esc(String(e))}).</p><p><a href="#/">☜ Library</a></p></main>`
    return () => {}
  }
  const g = await glossary
  if (!alive()) return () => {}
  const coll = collectionOf(lib, piece)
  /** A text with its technique words as buttons that open their definition card. */
  const linked = (text: string) => (g ? linkHtml(text, g, piece) : esc(text))
  const n = piece.voices.length
  const lastBeat = piece.notes.reduce((m, x) => Math.max(m, x.s + x.d), 0)
  const ensembleIds = Object.keys(ENSEMBLES) as EnsembleId[]

  let tuningId = localStorage.getItem('fugue.tuning') ?? DEFAULT_TUNING
  let shaped = localStorage.getItem('fugue.playing') !== 'plain'
  const nb = neighbours(lib, id)
  const titleOf = (pid: string) => summary(lib, pid)?.title ?? pid
  app.innerHTML = `<main class="sheet player">
    <nav class="phead"><a class="back" href="${coll ? collectionHref(coll.id) : '#/'}">☜ Library</a><span class="pos">${nb.prev ? `<a class="nb" href="#/p/${encodeURIComponent(nb.prev)}" aria-label="Previous: ${esc(titleOf(nb.prev))}" title="${esc(titleOf(nb.prev))}">‹</a>` : '<span class="nb off" aria-hidden="true">‹</span>'}<span class="pl">${esc(positionLabel(lib, id))}</span>${nb.next ? `<a class="nb" href="#/p/${encodeURIComponent(nb.next)}" aria-label="Next: ${esc(titleOf(nb.next))}" title="${esc(titleOf(nb.next))}">›</a>` : '<span class="nb off" aria-hidden="true">›</span>'}</span></nav>
    <h1 class="ptitle">${esc(piece.title)}</h1>
    <div class="pmeta">${esc([coll?.name, piece.catalogue].filter(Boolean).join(' · '))}</div>
    ${piece.listenFor ? `<p class="listen"><b>Listen for</b> ${linked(piece.listenFor)}</p>` : ''}
    <div class="roll"><canvas aria-label="Engraved roll of the music"></canvas></div>
    <p class="caption" aria-live="polite"></p>
    <div class="gcard" role="dialog" aria-labelledby="gcard-title" tabindex="-1" hidden></div>
    <div class="controls">
      <button type="button" class="ctl from-top"><span class="g" aria-hidden="true">⟲</span> from the top</button>
      <span class="barnav"><button type="button" class="ctl bar-step" data-d="-1" aria-label="Back one bar">‹</button><span class="barno">bar 1</span><button type="button" class="ctl bar-step" data-d="1" aria-label="Forward one bar">›</button></span>
      <button type="button" class="ctl loop" aria-pressed="false">loop</button>
      <button type="button" class="ctl btn play" disabled>loading…</button>
      <span class="tempo"><button type="button" class="ctl step" data-d="-1" aria-label="Slower">−</button><span class="bpm"></span><button type="button" class="ctl step" data-d="1" aria-label="Faster">+</button></span>
      <button type="button" class="ctl mark" aria-pressed="true"></button>
      <label class="ctl ens">ensemble: <select aria-label="Ensemble">${ensembleIds.map(e =>
        `<option value="${e}"${e === piece.ensemble ? ' selected' : ''}>${esc(ENSEMBLES[e].name.toLowerCase())}</option>`).join('')}</select><span class="caret" aria-hidden="true">▾</span></label>
      <label class="ctl ens">tuning: <select class="tuning" aria-label="Tuning">${TUNINGS.map(t =>
        `<option value="${t.id}"${t.id === tuningId ? ' selected' : ''}>${esc(t.name)}</option>`).join('')}</select><span class="caret" aria-hidden="true">▾</span></label><button type="button" class="ctl tune-help" aria-expanded="false" aria-controls="tune-note" aria-label="About the tunings">?</button>
      <label class="ctl ens">playing: <select class="style" aria-label="Playing">${['shaped', 'plain'].map(v =>
        `<option value="${v}"${(v === 'shaped') === shaped ? ' selected' : ''}>${v}</option>`).join('')}</select><span class="caret" aria-hidden="true">▾</span></label>
    </div>
    <div class="tune-note" id="tune-note" hidden>${TUNING_NOTE}</div>
    <div class="voices"></div>
    <div class="voices-hint">tap a voice to silence it · hold it to hear it alone · drag the roll to move</div>
  </main>`
  const $ = <T extends HTMLElement>(s: string) => app.querySelector<T>(s)!
  const canvas = $<HTMLCanvasElement>('canvas'), rollBox = $<HTMLDivElement>('.roll')
  const captionEl = $<HTMLParagraphElement>('.caption'), playBtn = $<HTMLButtonElement>('.play')
  const bpmEl = $<HTMLSpanElement>('.bpm'), markBtn = $<HTMLButtonElement>('.mark')
  const ensSel = $<HTMLSelectElement>('select'), voicesEl = $<HTMLDivElement>('.voices')
  const barEl = $<HTMLSpanElement>('.barno')
  const ctx2d = canvas.getContext('2d', { alpha: false })! // opaque: the roll paints its own paper
  const playerEl = $<HTMLElement>('.player'), cardEl = $<HTMLDivElement>('.gcard')
  /** Desktop: the card stands on the caption, right of the playhead, over the music still to come
   * (the caption, the playhead and what has sounded stay in view). Phone: a sheet from the bottom edge
   * (styles.css), so nothing to place. */
  function placeCard() {
    if (window.matchMedia('(max-width: 600px)').matches) return
    const top0 = rollBox.offsetTop, bottom = captionEl.offsetTop - 6
    cardEl.style.setProperty('--card-max', `${Math.max(200, bottom - top0)}px`)
    cardEl.style.setProperty('--card-top', `${Math.max(top0, bottom - cardEl.offsetHeight)}px`)
  }
  const card = g ? createCard(cardEl, g, { notes: piece.glossaryNotes, onShow: placeCard, onSound: on => duck(bus.gain, on, ctx.currentTime) }) : null

  // ---- sound ----
  const { ctx, sampler } = getAudio()
  /** The piece's own level: a glossary example ducks it while it sounds. */
  const bus = ctx.createGain()
  const room = makeRoom(ctx, ctx.destination)
  bus.connect(room.input)
  let ensemble = piece.ensemble
  let instruments = piece.voices.map(v => v.instrument)
  const pans = piece.voices.map(v => v.pan)
  const gain = 0.5 / Math.sqrt(n)
  const tempoKey = `fugue.tempo.${id}`
  const savedTempo = Number(localStorage.getItem(tempoKey))
  let tempo = savedTempo >= piece.tempo / 3 && savedTempo <= piece.tempo * 3 ? savedTempo : piece.tempo // the listener's own tempo for this piece
  /** Lowest and highest pitch of each voice, for choosing instruments that can play them. */
  const voiceRanges: [number, number][] = piece.voices.map((_, v) => {
    let lo = Infinity, hi = -Infinity
    for (const x of piece.notes) if (x.v === v) { lo = Math.min(lo, x.p); hi = Math.max(hi, x.p) }
    return [lo, hi]
  })
  let markings = true
  const gate = new LoadGate()
  let playing = false
  let resumeAfterLoad = false // the listener was playing when the ensemble changed
  let resumeBeat = 0 // where play continues from while paused
  let disposed = false
  const muted = new Set<number>() // voices switched off; a piece starts with all audible
  let loopA: number | null = null // loop start marked, end not yet
  let loop: { from: number; to: number; bars: [number, number] } | null = null
  let solo: number | null = null // the voice held down: heard alone while the press lasts
  let silent: ReadonlySet<number> = muted // what is actually silenced (and dimmed) right now
  const debug: Debug = { scheduled: 0, byVoice: piece.voices.map(() => 0), failed: 0, state: () => ctx.state, position: () => now() }
  if (import.meta.env.DEV) window.__listening = debug

  const play: PlayFn = (note, when, dur) => {
    // one bad note must never stop the scheduler's timer
    try {
      const ins = instruments[note.v]
      const last = shaped && note.s + note.d >= lastBeat - 1e-6 // the closing notes are held a little
      const loud = shaped ? accent(note.s, piece.beatsPerBar, piece.pickup ?? 0, ins) : 1
      const h = sampler.play(ins, note.p, when, last ? dur * FINAL_HOLD : dur, pans[note.v], gain * loud, bus,
        { tune: tuningFactor(note.p, tuningById(tuningId)), ...envelopeFor(ins, shaped) })
      debug.scheduled++
      if (import.meta.env.DEV) debug.byVoice[note.v]++
      return h
    } catch (e) {
      debug.failed++
      console.warn('note skipped', e)
    }
  }
  const scheduler = new Scheduler(() => ctx.currentTime, play, piece.notes, tempo)
  /** Switches one voice on or off: its sounding notes are released at once, its next ones are skipped (or played). */
  function toggleVoice(v: number) {
    if (!muted.delete(v)) muted.add(v)
    applySilence()
  }
  /** Heard alone while held; on release the listener's own on/off choices return. */
  function setSolo(v: number | null) {
    solo = v
    applySilence()
  }
  function applySilence() {
    silent = heardMuted(muted, solo, n)
    scheduler.setMuted(silent)
    syncVoices()
    draw()
  }
  /** Seconds between scheduling a sound and hearing it (iOS reports outputLatency; others baseLatency). */
  const latency = () => ctx.outputLatency || ctx.baseLatency || 0
  // the roll shows what is heard, not what is scheduled
  // drawn from a smoothed clock: Android advances the audio clock in steps of one buffer
  const drawClock = smoothClock(() => ctx.currentTime, () => performance.now())
  const heard = () => heardPosition(scheduler.positionAt(drawClock()), latency(), tempo)
  // and eased once per frame: no stall-and-jump or backward step when playback starts
  const smooth = positionFilter()
  let shownBeat = 0
  const now = () => (playing ? shownBeat : resumeBeat)

  /** Loads the current instruments' samples. True only for the latest load, and only if it succeeded. */
  async function loadSamples(): Promise<boolean> {
    const token = gate.begin()
    updateControls()
    const byInstr = new Map<string, number[]>()
    for (const note of piece.notes) {
      const ins = instruments[note.v]
      let ps = byInstr.get(ins)
      if (!ps) byInstr.set(ins, ps = [])
      ps.push(note.p)
    }
    try {
      await Promise.all([...byInstr].map(([ins, ps]) => sampler.load(ins, ps)))
      if (!gate.finish(token)) return false // a newer load owns the button
    } catch (e) {
      console.error(e)
      if (!gate.fail(token)) return false
    }
    if (disposed) return false
    updateControls()
    return !gate.failed
  }

  /** The room follows the instruments; plain playing is dry. */
  const setRoom = () => room.setLevel(shaped ? roomLevel(instruments) : 0)
  setRoom()

  // ---- timing ----
  let timer = 0, raf = 0
  function start() {
    if (playing || gate.loading || gate.failed || disposed) return
    if (resumeBeat >= lastBeat) resumeBeat = 0
    scheduler.start(resumeBeat)
    smooth.reset()
    playing = true
    noteHeard(id) // recently heard: only once it actually plays
    timer = window.setInterval(() => {
      scheduler.tick()
      if (loop && scheduler.position() >= loop.to) { scheduler.start(loop.from); smooth.reset() } // back to the loop's start
    }, 25)
    raf = requestAnimationFrame(frame)
    updateControls()
  }
  function pause() {
    if (!playing) return
    // stop where the listener is, not where scheduling has got to: the notes in the output-latency window replay on resume
    scheduler.pause(heardPosition(scheduler.position(), latency(), tempo))
    resumeBeat = Math.min(scheduler.position(), lastBeat)
    playing = false
    clearInterval(timer)
    cancelAnimationFrame(raf)
    updateControls()
    draw()
  }
  let lastFrame = 0
  function frame(t: number) {
    if (!playing) return
    if (scheduler.position() >= lastBeat + 0.5) { pause(); resumeBeat = lastBeat; draw(); return }
    if (t - lastFrame >= FRAME_MS - 1) { lastFrame = t; draw() } // fast screens: skip frames past ~60 per second
    raf = requestAnimationFrame(frame)
  }
  function requestPlay() {
    // resume inside the gesture (iOS); 'interrupted' (iOS calls, Siri) is treated like 'suspended'
    if (ctx.state !== 'running') {
      ctx.resume().then(() => { if (ctx.state === 'running') start() }, () => {})
    } else start()
  }
  const onState = () => { if (ctx.state !== 'running') pause() }
  ctx.addEventListener('statechange', onState)
  // screen locked or tab hidden: keep playing (lock-screen controls below), with a longer look-ahead for late timers
  const onVisibility = () => {
    scheduler.setLookahead(document.visibilityState === 'hidden' ? BACKGROUND_LOOKAHEAD : LOOKAHEAD)
    if (playing) scheduler.tick()
  }
  document.addEventListener('visibilitychange', onVisibility)
  const unHidden = () => document.removeEventListener('visibilitychange', onVisibility)

  // ---- drawing ----
  let layout: Layout | null = null
  let lastCaption = ''
  /** The labels drawn in the last frame, for taps. */
  let labels: LabelHit[] = []
  function resize() {
    const w = rollBox.clientWidth, h = rollBox.clientHeight
    if (w < 10 || h < 10) return
    const dpr = canvasDpr(window.devicePixelRatio)
    canvas.width = Math.round(w * dpr); canvas.height = Math.round(h * dpr)
    canvas.style.width = `${w}px`; canvas.style.height = `${h}px`
    layout = layoutFor(piece, w, h, dpr)
    draw()
  }
  function draw() {
    if (playing) shownBeat = smooth.next(heard(), performance.now(), tempo / 60)
    const t = now()
    labels = []
    if (layout) {
      drawRoll(ctx2d, piece, layout, t, { markings, muted: silent, labels })
      if (loop) drawRepeatSigns(ctx2d, layout, t, loop.from, loop.to)
      else if (loopA !== null) drawRepeatSigns(ctx2d, layout, t, barStart(piece, barOf(piece, loopA)), null)
    }
    const bar = `bar ${Math.max(1, barOf(piece, t))}`
    if (barEl.textContent !== bar) barEl.textContent = bar
    const cap = captionAt(piece.captions, t)
    if (cap !== lastCaption) { lastCaption = cap; captionEl.innerHTML = linked(cap) }
  }
  const ro = new ResizeObserver(resize)
  ro.observe(rollBox)
  document.fonts.load(`italic 13px 'EB Garamond'`).then(() => draw(), () => {})

  // ---- controls ----
  function updateControls() {
    playBtn.disabled = gate.loading
    playBtn.classList.toggle('failed', gate.failed)
    playBtn.textContent = gate.loading ? 'loading…' : gate.failed ? 'could not load — tap to retry'
      : playing ? '❚❚ Pause' : '▶ Play'
    bpmEl.textContent = tempoLabel(tempo, piece.beatUnit)
    if ('mediaSession' in navigator) navigator.mediaSession.playbackState = playing ? 'playing' : 'paused'
    markBtn.textContent = `markings: ${markings ? 'on' : 'off'}`
    markBtn.setAttribute('aria-pressed', String(markings))
    voicesEl.innerHTML = piece.voices.map((v, i) =>
      `<button type="button" class="voice" data-v="${i}" aria-pressed="${!muted.has(i)}"><i class="sw ${v.texture}" aria-hidden="true"></i><span class="nm">${esc(v.name)} · ${esc(instruments[i])}</span></button>`).join('')
  }
  /** Reflects the muted set on the key in place (keeps keyboard focus on the pressed entry). */
  function syncVoices() {
    for (const b of voicesEl.querySelectorAll<HTMLButtonElement>('.voice')) {
      const v = Number(b.dataset.v)
      b.setAttribute('aria-pressed', String(!muted.has(v)))
      b.classList.toggle('solo', solo === v)
      b.classList.toggle('hushed', solo !== null && solo !== v)
    }
  }
  voicesEl.addEventListener('click', (e) => {
    const b = (e.target as Element).closest<HTMLButtonElement>('.voice')
    if (b) toggleVoice(Number(b.dataset.v))
  })
  const unHoldKey = pressAndHold(voicesEl, (e) => {
    const b = (e.target as Element).closest<HTMLButtonElement>('.voice')
    return b ? Number(b.dataset.v) : null
  }, setSolo, () => setSolo(null))
  const unHoldRoll = pressAndHold(canvas, (e) => {
    if (!layout) return null
    const r = canvas.getBoundingClientRect()
    return voiceAt(piece, layout, now(), e.clientX - r.left, e.clientY - r.top)
  }, setSolo, () => setSolo(null))
  canvas.addEventListener('click', (e) => {
    if (!layout) return
    const r = canvas.getBoundingClientRect()
    const x = e.clientX - r.left, y = e.clientY - r.top
    // a label opens its card, unless the tap is right on a note and only near the lettering
    const lab = g && card ? labelAt(labels, x, y) : null
    if (lab) {
      const onText = x >= lab.x - 2 && x <= lab.x + lab.w + 2 && y >= lab.y && y <= lab.y + lab.h
      const ids = labelEntries(lab.mark, lab.text, piece, g!)
      if (ids.length && (onText || voiceAt(piece, layout, now(), x, y, 0) === null)) {
        card!.open(ids, undefined, canvas)
        return
      }
    }
    if (card?.dismissedBy(e)) return // this tap only closed the card
    const v = voiceAt(piece, layout, now(), x, y)
    if (v !== null) toggleVoice(v)
  })
  // a technique word in the caption or the "listen for" line
  playerEl.addEventListener('click', (e) => {
    const b = (e.target as Element).closest<HTMLButtonElement>('button.term')
    if (b && card) card.open([b.dataset.entry ?? ''], b.dataset.term, b)
  })
  playBtn.addEventListener('click', () => {
    if (gate.failed) void loadSamples().then(ok => { if (ok && resumeAfterLoad) { resumeAfterLoad = false; requestPlay() } })
    else if (playing) pause()
    else requestPlay()
  })
  $<HTMLButtonElement>('.from-top').addEventListener('click', () => seekTo(0))
  /** Moves playback (or the paused position) to `beat`. */
  function seekTo(beat: number) {
    const b = Math.min(lastBeat, Math.max(0, beat))
    if (playing) { scheduler.start(b); smooth.reset() }
    else resumeBeat = b
    draw()
  }
  for (const b of app.querySelectorAll<HTMLButtonElement>('.bar-step')) {
    b.addEventListener('click', () => seekTo(b.dataset.d === '1' ? nextBarBeat(piece, now(), lastBeat) : prevBarBeat(piece, now())))
  }
  // ---- loop: first tap marks the bar it starts in, second tap the bar it ends in; a third tap clears it ----
  const loopBtn = $<HTMLButtonElement>('.loop')
  function syncLoop() {
    loopBtn.setAttribute('aria-pressed', String(loop !== null || loopA !== null))
    loopBtn.textContent = loop ? `loop: bars ${loop.bars[0]}–${loop.bars[1]}` : loopA !== null ? `loop from bar ${Math.max(1, barOf(piece, loopA))}… tap at its end` : 'loop'
  }
  loopBtn.addEventListener('click', () => {
    if (loop) { loop = null }
    else if (loopA === null) { loopA = now() }
    else {
      loop = loopRange(piece, loopA, now(), lastBeat)
      loopA = null
      if (now() >= loop.to || now() < loop.from) seekTo(loop.from)
    }
    syncLoop()
    draw()
  })
  // ---- drag the roll to move through the piece ----
  const DRAG_PX = 12 // past the press-and-hold slop, so a hold never turns into a drag
  let drag: { x0: number; b0: number; id: number; active: boolean; wasPlaying: boolean } | null = null
  let dragged = false
  canvas.addEventListener('pointerdown', (e) => {
    if (e.button !== 0 || !layout) return
    dragged = false
    drag = { x0: e.clientX, b0: now(), id: e.pointerId, active: false, wasPlaying: playing }
  })
  canvas.addEventListener('pointermove', (e) => {
    if (!drag || !layout || e.pointerId !== drag.id) return
    const dx = e.clientX - drag.x0
    if (!drag.active) {
      if (Math.abs(dx) < DRAG_PX) return
      drag.active = true
      try { canvas.setPointerCapture(drag.id) } catch { /* gone */ }
      if (playing) pause()
    }
    resumeBeat = dragBeat(drag.b0, dx, layout.beatWidth, lastBeat)
    draw()
  })
  const endDrag = () => {
    if (drag?.active) { dragged = true; if (drag.wasPlaying) requestPlay() }
    drag = null
  }
  canvas.addEventListener('pointerup', endDrag)
  canvas.addEventListener('pointercancel', endDrag)
  canvas.addEventListener('click', (e) => { if (dragged) { dragged = false; e.stopImmediatePropagation() } }, true)
  // ---- keyboard: space plays/pauses, arrows move a bar, L marks the loop ----
  const onKey = (e: KeyboardEvent) => {
    const t = e.target as HTMLElement | null
    if (e.metaKey || e.ctrlKey || e.altKey || (t && /^(INPUT|SELECT|TEXTAREA)$/.test(t.tagName))) return
    if (e.key === ' ') { e.preventDefault(); playBtn.click() } // always play/pause, as in media players (Enter still presses a focused button)
    else if (e.key === 'ArrowLeft') { e.preventDefault(); seekTo(prevBarBeat(piece, now())) }
    else if (e.key === 'ArrowRight') { e.preventDefault(); seekTo(nextBarBeat(piece, now(), lastBeat)) }
    else if (e.key === 'l' || e.key === 'L') loopBtn.click()
    else if (e.key === '[' && nb.prev) location.hash = `#/p/${encodeURIComponent(nb.prev)}`
    else if (e.key === ']' && nb.next) location.hash = `#/p/${encodeURIComponent(nb.next)}`
  }
  document.addEventListener('keydown', onKey)
  // ---- lock screen / headphone controls ----
  const ms = 'mediaSession' in navigator ? navigator.mediaSession : null
  const msActions: [MediaSessionAction, MediaSessionActionHandler][] = [
    ['play', () => requestPlay()],
    ['pause', () => pause()],
    ['stop', () => { pause(); seekTo(0) }],
    ['seekbackward', () => seekTo(prevBarBeat(piece, now()))],
    ['seekforward', () => seekTo(nextBarBeat(piece, now(), lastBeat))],
    ['previoustrack', () => seekTo(0)],
  ]
  if (ms) {
    ms.metadata = new MediaMetadata({ title: piece.title, artist: 'J. S. Bach', album: [coll?.name, piece.catalogue].filter(Boolean).join(' · ') })
    for (const [a, h] of msActions) { try { ms.setActionHandler(a, h) } catch { /* not supported here */ } }
  }
  for (const b of app.querySelectorAll<HTMLButtonElement>('.step')) {
    b.addEventListener('click', () => {
      tempo = stepTempo(tempo, Number(b.dataset.d) as 1 | -1, piece.tempo)
      if (tempo === piece.tempo) localStorage.removeItem(tempoKey); else localStorage.setItem(tempoKey, String(tempo))
      scheduler.setTempo(tempo) // keeps the position
      updateControls()
    })
  }
  markBtn.addEventListener('click', () => { markings = !markings; updateControls(); draw() })
  ensSel.addEventListener('change', async () => {
    resumeAfterLoad ||= playing
    pause()
    ensemble = ensSel.value
    instruments = ensemble === piece.ensemble ? piece.voices.map(v => v.instrument) : instrumentsForRanges(ensemble, voiceRanges)
    setRoom()
    // only the latest switch may resume (A → B → C: A's and B's loads end quietly)
    if (await loadSamples() && resumeAfterLoad) { resumeAfterLoad = false; requestPlay() }
  })

  const tuneHelp = $<HTMLButtonElement>('.tune-help'), tuneNote = $<HTMLDivElement>('.tune-note')
  const markTuning = () => { for (const el of tuneNote.querySelectorAll<HTMLElement>('[data-tuning]')) el.classList.toggle('on', el.dataset.tuning === tuningId) }
  markTuning()
  const showTuneNote = (on: boolean) => { tuneNote.hidden = !on; tuneHelp.setAttribute('aria-expanded', String(on)) }
  tuneHelp.addEventListener('click', () => showTuneNote(tuneNote.hidden !== false))
  // closes on Escape or a tap anywhere outside it
  const closeTuneNote = (e: Event) => {
    if (tuneNote.hidden) return
    if (e instanceof KeyboardEvent ? e.key === 'Escape' : !tuneNote.contains(e.target as Node) && e.target !== tuneHelp) showTuneNote(false)
  }
  document.addEventListener('keydown', closeTuneNote)
  document.addEventListener('pointerdown', closeTuneNote)
  $<HTMLSelectElement>('select.tuning').addEventListener('change', (e) => {
    tuningId = (e.target as HTMLSelectElement).value
    markTuning()
    localStorage.setItem('fugue.tuning', tuningId)
  })
  $<HTMLSelectElement>('select.style').addEventListener('change', (e) => {
    shaped = (e.target as HTMLSelectElement).value === 'shaped'
    localStorage.setItem('fugue.playing', shaped ? 'shaped' : 'plain')
    setRoom()
  })

  updateControls()
  void loadSamples()

  return () => {
    disposed = true
    card?.dispose()
    pause()
    window.setTimeout(() => { bus.disconnect(); room.disconnect() }, 3000) // after the released notes have faded
    ro.disconnect()
    unHidden()
    unHoldKey()
    unHoldRoll()
    document.removeEventListener('keydown', onKey)
    document.removeEventListener('keydown', closeTuneNote)
    document.removeEventListener('pointerdown', closeTuneNote)
    if (ms) { for (const [a] of msActions) { try { ms.setActionHandler(a, null) } catch { /* */ } } ms.playbackState = 'none' }
    ctx.removeEventListener('statechange', onState)
    if (window.__listening === debug) delete window.__listening
  }
}

/** Engraved repeat signs at a loop's ends (‖: and :‖), drawn over the roll. `to` null: only the start is marked yet. */
function drawRepeatSigns(ctx: CanvasRenderingContext2D, L: Layout, now: number, from: number, to: number | null) {
  ctx.save()
  ctx.strokeStyle = INK
  ctx.fillStyle = INK
  const mid = (L.top + L.bottom) / 2
  const sign = (beat: number, open: boolean) => {
    const x = L.x(beat, now)
    if (x < -10 || x > L.width + 10) return
    const thick = open ? x : x - 4, thin = open ? x + 4 : x
    ctx.globalAlpha = 0.55
    ctx.lineWidth = 2.2; ctx.beginPath(); ctx.moveTo(thick, L.top); ctx.lineTo(thick, L.bottom); ctx.stroke()
    ctx.lineWidth = 0.7; ctx.beginPath(); ctx.moveTo(thin, L.top); ctx.lineTo(thin, L.bottom); ctx.stroke()
    const dx = open ? x + 8 : x - 8
    for (const dy of [-6, 6]) { ctx.beginPath(); ctx.arc(dx, mid + dy, 1.8, 0, Math.PI * 2); ctx.fill() }
  }
  sign(from, true)
  if (to !== null) sign(to, false)
  ctx.restore()
}

/** What the tuning menu's options mean, and what to listen for. */
const TUNING_NOTE = `
<p class="tn-head">Tuning: how far apart the twelve notes of the octave are set</p>
<dl>
  <dt data-tuning="equal">Equal · a′ 440</dt>
  <dd data-tuning="equal">Today's tuning. All twelve fifths are narrowed by the same tiny amount, so every key sounds alike;
  the major thirds are noticeably wide everywhere. a′ = 440 Hz is modern concert pitch.</dd>
  <dt data-tuning="vallotti">Vallotti · a′ 415</dt>
  <dd data-tuning="vallotti">An 18th-century “good” temperament (Francesco Antonio Vallotti). Six fifths, F–C–G–D–A–E–B, are
  narrowed by a sixth of a comma; the other six are pure. Every key is usable, but they differ: keys with few sharps or
  flats have calmer thirds, remote ones are more restless.</dd>
  <dt data-tuning="werckmeister">Werckmeister III · a′ 415</dt>
  <dd data-tuning="werckmeister">Andreas Werckmeister, 1691, a generation before Bach. Only four fifths are narrowed, by a
  quarter of a comma; the rest are pure. C major and its neighbours sound sweet; far keys such as F♯ major or E♭ minor
  have a sharper edge. The contrast between keys is stronger than in Vallotti.</dd>
</dl>
<p><b>a′ 415</b>: about a semitone below modern pitch, the usual convention for baroque music today (in Bach's time pitch
varied from town to town). What Bach himself meant by “well-tempered” is still debated; both old tunings let all 24 keys
of the book sound, each with its own colour.</p>
<p><b>Listen:</b> play a fugue in C major, then one in a far key (F♯ major, E♭ minor), first in equal, then in
Werckmeister. In equal they sound alike; in Werckmeister the far key sounds tenser. The change applies from the next notes.</p>
`
