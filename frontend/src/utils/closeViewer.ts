export async function closeViewerAfterFullscreen(
  exitNative: (() => Promise<unknown>) | undefined,
  close: () => void,
) {
  try {
    await exitNative?.()
    if (document.fullscreenElement && document.exitFullscreen) await document.exitFullscreen()
  } catch (error) {
    console.warn('退出查看器全屏失败', error)
  } finally {
    close()
  }
}
