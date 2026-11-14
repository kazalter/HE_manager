import type { DesktopBridge, ImageEnhancement } from '../desktop-contract'

/** UI-facing optional capabilities. Platform internals remain behind the bridge. */
export function createPlatformCapabilities(bridge: Partial<DesktopBridge> | undefined) {
  return {
    imageEnhancement: typeof bridge?.enhanceImage === 'function' ? {
      enhance: (url: string, mode: Exclude<ImageEnhancement, 'off'>) => bridge.enhanceImage!({ url, mode }),
    } : null,
    embeddedVideo: typeof bridge?.openVideo === 'function' && typeof bridge?.mountVideoSurface === 'function',
  }
}
