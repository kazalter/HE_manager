import { describe, expect, it, vi } from 'vitest'
import { createPlatformCapabilities } from '../platform/capabilities'

describe('platform capabilities', () => {
  it('exposes no native enhancement or embedded player on the web', () => {
    const capabilities = createPlatformCapabilities(undefined)
    expect(capabilities.imageEnhancement).toBeNull()
    expect(capabilities.embeddedVideo).toBe(false)
  })
  it('invokes the desktop image capability without exposing IPC details', async () => {
    const enhanceImage = vi.fn().mockResolvedValue({ url: 'he://app/image', cached: true, scale: 2 })
    const capabilities = createPlatformCapabilities({ enhanceImage, openVideo: vi.fn(), mountVideoSurface: vi.fn() })
    expect(capabilities.embeddedVideo).toBe(true)
    await expect(capabilities.imageEnhancement!.enhance('/stream/1', 'anime')).resolves.toMatchObject({ scale: 2 })
    expect(enhanceImage).toHaveBeenCalledWith({ url: '/stream/1', mode: 'anime' })
  })
  it('gracefully handles older bridges without optional capabilities', () => {
    expect(createPlatformCapabilities({}).imageEnhancement).toBeNull()
    expect(createPlatformCapabilities({ openVideo: vi.fn() }).embeddedVideo).toBe(false)
  })
})
