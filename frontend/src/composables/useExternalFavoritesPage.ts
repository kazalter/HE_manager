import { computed, onUnmounted, ref, watch, type Ref } from 'vue'
import axios from 'axios'
import { API_BASE_URL } from '../config'
import type { ExternalFavoriteItem } from '../types'

interface ExternalFavoritesPageOptions {
  sourceType: 'wnacg' | 'asmr'
  activeSourceId: Ref<number | null>
  searchQuery: Ref<string>
  pageSize?: number
  searchDelayMs?: number
  onSearchReset?: () => void
}

/** Shared server-side filtering/pagination for external-source panels. */
export function useExternalFavoritesPage(options: ExternalFavoritesPageOptions) {
  const pageSize = options.pageSize ?? 15
  const items = ref<ExternalFavoriteItem[]>([])
  const totalItems = ref(0)
  const currentPage = ref(1)
  const loading = ref(false)
  const error = ref('')
  let requestId = 0
  let searchTimer: ReturnType<typeof setTimeout> | undefined

  const totalPages = computed(() => Math.max(1, Math.ceil(totalItems.value / pageSize)))
  const pageStart = computed(() => totalItems.value === 0 ? 0 : (currentPage.value - 1) * pageSize + 1)
  const pageEnd = computed(() => Math.min(currentPage.value * pageSize, totalItems.value))

  const fetchItems = async (resetPage = false) => {
    if (resetPage) currentPage.value = 1
    const activeRequest = ++requestId
    loading.value = true
    error.value = ''
    try {
      const response = await axios.get<ExternalFavoriteItem[]>(`${API_BASE_URL}/external/favorites`, {
        params: {
          source_type: options.sourceType,
          source_id: options.activeSourceId.value || undefined,
          search: options.searchQuery.value.trim() || undefined,
          limit: pageSize,
          offset: (currentPage.value - 1) * pageSize,
        },
      })
      if (activeRequest !== requestId) return
      items.value = response.data
      totalItems.value = Number(response.headers['x-total-count'] || response.data.length)
      const lastPage = Math.max(1, Math.ceil(totalItems.value / pageSize))
      if (currentPage.value > lastPage) {
        currentPage.value = lastPage
        await fetchItems()
      }
    } catch (err) {
      if (activeRequest !== requestId) return
      console.error(`Failed to fetch ${options.sourceType} favorites:`, err)
      error.value = options.sourceType === 'asmr' ? '读取 ASMR 收藏失败' : '读取外部收藏失败'
    } finally {
      if (activeRequest === requestId) loading.value = false
    }
  }

  const setPage = (page: number) => {
    const target = Math.min(Math.max(page, 1), totalPages.value)
    if (target === currentPage.value) return false
    currentPage.value = target
    void fetchItems()
    return true
  }

  watch(options.searchQuery, () => {
    if (searchTimer) clearTimeout(searchTimer)
    searchTimer = setTimeout(() => {
      options.onSearchReset?.()
      void fetchItems(true)
    }, options.searchDelayMs ?? 300)
  })

  onUnmounted(() => {
    requestId++
    if (searchTimer) clearTimeout(searchTimer)
  })

  return {
    items,
    totalItems,
    currentPage,
    loading,
    error,
    totalPages,
    pageStart,
    pageEnd,
    pageSize,
    fetchItems,
    setPage,
  }
}
