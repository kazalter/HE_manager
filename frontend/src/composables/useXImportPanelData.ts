import { onMounted, onUnmounted, ref, type Ref } from 'vue'
import axios from 'axios'
import { API_BASE_URL } from '../config'
import { xImportStore } from '../stores/xImportStore'
import type { XImportSource, XPost } from '../types'

/** Owns X panel request/subscription lifecycle; the component keeps only UI actions. */
export function useXImportPanelData(downloadRootPath: Ref<string>) {
  const failedPosts = ref<XPost[]>([])
  const failedLoading = ref(false)
  let unsubscribe: (() => void) | null = null

  const fetchFailedPosts = async () => {
    const source = xImportStore.source.value
    if (!source) return
    failedLoading.value = true
    try {
      const response = await axios.get<XPost[]>(`${API_BASE_URL}/x/sources/${source.id}/posts`, {
        params: { status: 'failed', limit: 100 },
      })
      failedPosts.value = response.data
    } catch (err) {
      console.error('Failed to fetch failed posts:', err)
    } finally {
      failedLoading.value = false
    }
  }

  const updateAutoSync = async (payload: { auto_sync_enabled?: boolean; auto_sync_interval_hours?: number }) => {
    const source = xImportStore.source.value
    if (!source) return
    try {
      const response = await axios.patch(`${API_BASE_URL}/auto-sync/x/${source.id}`, payload)
      xImportStore.state.source = response.data as XImportSource
    } catch (err: any) {
      xImportStore.setError(err.response?.data?.detail || '更新自动同步配置失败')
    }
  }

  onMounted(async () => {
    await xImportStore.fetchSource()
    if (xImportStore.source.value?.download_root_path) {
      downloadRootPath.value = xImportStore.source.value.download_root_path
    }
    await xImportStore.ensureResumed()
    unsubscribe = xImportStore.onCompleted(async () => {
      const source = xImportStore.source.value
      if (source) await xImportStore.refreshStats(source.id)
      await fetchFailedPosts()
    })
    await fetchFailedPosts()
  })

  onUnmounted(() => {
    unsubscribe?.()
    unsubscribe = null
  })

  return { failedPosts, failedLoading, fetchFailedPosts, updateAutoSync }
}
