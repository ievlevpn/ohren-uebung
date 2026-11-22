import { describe, expect, it } from 'vitest'
import { unlockAudio } from './sampler'

describe('unlockAudio', () => {
  it('ignores pointerdown, retries until the context is running, then stops listening', async () => {
    const target = new EventTarget()
    let calls = 0
    const ctx = { state: 'suspended', async resume() { calls++; if (calls >= 2) this.state = 'running' } }
    unlockAudio(ctx, target)
    const fire = async (type: string) => { target.dispatchEvent(new Event(type)); await Promise.resolve(); await Promise.resolve() }
    await fire('pointerdown')
    expect(calls).toBe(0)
    await fire('touchend') // resume resolves but state still suspended: keep listening
    expect(calls).toBe(1)
    await fire('click') // now running: listeners removed
    expect(calls).toBe(2)
    await fire('click')
    await fire('keydown')
    expect(calls).toBe(2)
  })
})
