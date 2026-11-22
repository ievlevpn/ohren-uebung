/** What `navigator` offers for routing Web Audio past the iPhone ring/silent switch. */
export interface NavLike { audioSession?: { type: string }; userAgent: string; platform: string; maxTouchPoints: number }

/**
 * iOS mutes Web Audio when the silent switch is on unless the page's audio session is "playback".
 * Safari 16.4+ lets us say so (navigator.audioSession). Older iOS: playing any <audio> element switches the session,
 * so the caller starts a looping silent one on the unlock gesture. Desktops have no switch.
 */
export function playThroughSilentSwitch(nav: NavLike): 'audioSession' | 'silentAudio' | 'none' {
  if (nav.audioSession) { nav.audioSession.type = 'playback'; return 'audioSession' }
  const ios = /iPad|iPhone|iPod/.test(nav.userAgent) || (nav.platform === 'MacIntel' && nav.maxTouchPoints > 1)
  return ios ? 'silentAudio' : 'none'
}

/** A short silent WAV (8 kHz, 8-bit mono, 0.25 s) as a blob URL. */
function silentWav(): string {
  const n = 2000, b = new DataView(new ArrayBuffer(44 + n))
  const str = (o: number, s: string) => { for (let i = 0; i < s.length; i++) b.setUint8(o + i, s.charCodeAt(i)) }
  str(0, 'RIFF'); b.setUint32(4, 36 + n, true); str(8, 'WAVEfmt '); b.setUint32(16, 16, true)
  b.setUint16(20, 1, true); b.setUint16(22, 1, true); b.setUint32(24, 8000, true); b.setUint32(28, 8000, true)
  b.setUint16(32, 1, true); b.setUint16(34, 8, true); str(36, 'data'); b.setUint32(40, n, true)
  for (let i = 0; i < n; i++) b.setUint8(44 + i, 128) // 8-bit silence
  return URL.createObjectURL(new Blob([b.buffer], { type: 'audio/wav' }))
}

/** Starts a looping silent <audio> on the first gesture that lets it play (older iOS fallback). */
export function silentAudioOnGesture(target: EventTarget = document): void {
  const el = document.createElement('audio')
  el.src = silentWav()
  el.loop = true
  el.setAttribute('playsinline', '')
  el.setAttribute('x-webkit-airplay', 'deny')
  const events = ['touchend', 'click', 'keydown']
  const go = () => {
    el.play().then(() => { for (const e of events) target.removeEventListener(e, go) }, () => { /* retry next gesture */ })
  }
  for (const e of events) target.addEventListener(e, go)
}
