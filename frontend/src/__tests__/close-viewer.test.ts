import { expect, it, vi } from 'vitest'
import { closeViewerAfterFullscreen } from '../utils/closeViewer'

it('waits for the desktop fullscreen exit before closing the viewer', async () => {
  let finish!: () => void
  const exit = vi.fn(() => new Promise<void>(resolve => { finish = resolve }))
  const close = vi.fn()
  const pending = closeViewerAfterFullscreen(exit, close)
  expect(exit).toHaveBeenCalledOnce()
  expect(close).not.toHaveBeenCalled()
  finish()
  await pending
  expect(close).toHaveBeenCalledOnce()
})
