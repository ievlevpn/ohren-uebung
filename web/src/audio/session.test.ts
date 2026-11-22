import { describe, expect, it } from 'vitest'
import { playThroughSilentSwitch } from './session'

describe('playThroughSilentSwitch', () => {
  it('uses navigator.audioSession when there is one (Safari 16.4+)', () => {
    const nav = { audioSession: { type: 'auto' }, userAgent: 'iPhone', platform: 'iPhone', maxTouchPoints: 5 }
    expect(playThroughSilentSwitch(nav)).toBe('audioSession')
    expect(nav.audioSession.type).toBe('playback')
  })
  it('older iOS: needs the silent media element', () => {
    expect(playThroughSilentSwitch({ userAgent: 'Mozilla/5.0 (iPhone; CPU iPhone OS 15_7)', platform: 'iPhone', maxTouchPoints: 5 })).toBe('silentAudio')
    expect(playThroughSilentSwitch({ userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 5 })).toBe('silentAudio') // iPadOS
  })
  it('desktops have no silent switch: nothing to do', () => {
    expect(playThroughSilentSwitch({ userAgent: 'Mozilla/5.0 (Macintosh)', platform: 'MacIntel', maxTouchPoints: 0 })).toBe('none')
    expect(playThroughSilentSwitch({ userAgent: 'Mozilla/5.0 (X11; Linux)', platform: 'Linux x86_64', maxTouchPoints: 0 })).toBe('none')
  })
})
