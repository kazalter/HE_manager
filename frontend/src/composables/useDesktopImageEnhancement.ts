import { onBeforeUnmount, reactive, ref, watch } from 'vue'
import { desktopBridge, desktopState } from '../desktop'
/** Enhance only the visible spread. The existing original-image buffer remains intact. */
export function useDesktopImageEnhancement(visibleUrls: () => string[]) {
 const enhanced = reactive(new Map<string, string>())
 const message = ref('')
 let generation = 0, disposed = false
 watch([visibleUrls, () => desktopState.imageMode], async ([urls, mode]) => {
  const epoch = ++generation
  if (!desktopBridge || mode === 'off') { message.value = ''; return }
  message.value = '正在排队或处理，先显示原图…'
  let lastError = '', completed = 0
  for (const url of urls) {
   if (disposed || epoch !== generation) return
   try {
    const result = await desktopBridge.enhanceImage({ url, mode })
    if (disposed || epoch !== generation) return
    enhanced.set(`${mode}:${url}`, result.url); completed++
    while (enhanced.size > 24) enhanced.delete(enhanced.keys().next().value!)
    } catch (e: any) {
    const detail = String(e?.message || '').replace(/^Error invoking remote method '[^']+': (?:Error: )?/, '')
    lastError = /abort|aborted|中止|退出/i.test(detail)
      ? '超分任务已中止，当前显示原图；请重新打开应用后重试。'
      : detail || '图片超分失败，当前显示原图。'
   }
  }
  if (!disposed && epoch === generation) message.value = lastError || (completed ? '已显示本机超分画面' : '')
 }, { immediate: true })
 onBeforeUnmount(() => { disposed = true; generation++ })
 return { message, displayUrl: (original: string) => desktopState.imageMode === 'off' ? original : enhanced.get(`${desktopState.imageMode}:${original}`) || original }
}
