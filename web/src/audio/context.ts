import { Sampler, unlockAudio } from './sampler'
import { playThroughSilentSwitch, silentAudioOnGesture, type NavLike } from './session'

interface Audio { ctx: AudioContext; sampler: Sampler }
let audio: Audio | null = null

/** One AudioContext and sampler for the whole app (buffers are shared between pieces). Created suspended. */
export function getAudio(): Audio {
  if (!audio) {
    const Ctor = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext
    const ctx = new Ctor({ latencyHint: 'playback' })
    unlockAudio(ctx)
    // sound even with the iPhone silent switch on (a listening app, not a game)
    if (playThroughSilentSwitch(navigator as unknown as NavLike) === 'silentAudio') silentAudioOnGesture()
    audio = { ctx, sampler: new Sampler(ctx, 'samples/') }
  }
  return audio
}
