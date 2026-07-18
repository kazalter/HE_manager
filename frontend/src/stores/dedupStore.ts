import { computed, reactive } from 'vue'
import axios from 'axios'
import { API_BASE_URL } from '../config'
import type { DedupCandidatePage, DedupSummary, DuplicateCandidatePair } from '../types'

interface DedupState {
  summary: DedupSummary | null
  pairs: DuplicateCandidatePair[]
  loading: boolean
  errorMessage: string
  filterLevel: '' | 'strong_duplicate' | 'suspected_duplicate' | 'weak_suspected'
  filterStatus: 'pending' | 'all' | 'merged' | 'kept_both' | 'ignored' | 'replaced'
  filterMediaType: '' | 'video' | 'manga' | 'image' | 'audio'
  sort: 'confidence' | 'newest' | 'oldest'
  page: number
  pageSize: number
  total: number
}

const state = reactive<DedupState>({
  summary: null,
  pairs: [],
  loading: false,
  errorMessage: '',
  filterLevel: '',
  filterStatus: 'pending',
  filterMediaType: '',
  sort: 'confidence',
  page: 1,
  pageSize: 20,
  total: 0,
})

let pairsRequestId = 0
let pairsController: AbortController | null = null

const fetchSummary = async () => {
  try {
    const res = await axios.get<DedupSummary>(`${API_BASE_URL}/dedup/summary`)
    state.summary = res.data
  } catch (err: any) {
    state.errorMessage = err.response?.data?.detail || '读取去重统计失败'
  }
}

const fetchPairs = async () => {
  pairsController?.abort()
  pairsController = new AbortController()
  const requestId = ++pairsRequestId
  state.loading = true
  state.errorMessage = ''
  try {
    const res = await axios.get<DedupCandidatePage>(`${API_BASE_URL}/dedup/candidates-page`, {
      signal: pairsController.signal,
      params: {
        level: state.filterLevel || undefined,
        status: state.filterStatus,
        media_type: state.filterMediaType || undefined,
        sort: state.sort,
        limit: state.pageSize,
        offset: (state.page - 1) * state.pageSize,
      },
    })
    if (requestId !== pairsRequestId) return
    state.pairs = res.data.items
    state.total = res.data.total
    const lastPage = Math.max(1, Math.ceil(state.total / state.pageSize))
    if (state.page > lastPage) {
      state.page = lastPage
      await fetchPairs()
    }
  } catch (err: any) {
    if (axios.isCancel(err) || err?.code === 'ERR_CANCELED') return
    state.errorMessage = err.response?.data?.detail || '读取重复列表失败'
  } finally {
    if (requestId === pairsRequestId) state.loading = false
  }
}

const refresh = async () => {
  await Promise.all([fetchSummary(), fetchPairs()])
}

const resolvePair = async (
  pairId: number,
  action: 'keep_existing' | 'replace_path' | 'keep_both' | 'ignore',
  note?: string,
) => {
  try {
    await axios.post<DuplicateCandidatePair>(`${API_BASE_URL}/dedup/candidates/${pairId}/resolve`, {
      action,
      note: note || undefined,
    })
    state.pairs = state.pairs.filter(pair => pair.id !== pairId || state.filterStatus !== 'pending')
    await refresh()
  } catch (err: any) {
    state.errorMessage = err.response?.data?.detail || '处理失败'
    throw err
  }
}

const recheckMedia = async (mediaId: number) => {
  try {
    await axios.post(`${API_BASE_URL}/dedup/media/${mediaId}/recheck`)
    await refresh()
  } catch (err: any) {
    state.errorMessage = err.response?.data?.detail || '重新检测失败'
  }
}

const deleteMediaFile = async (mediaId: number) => {
  try {
    await axios.delete(`${API_BASE_URL}/dedup/media/${mediaId}/file`, {
      data: { confirm: true },
    })
    await refresh()
  } catch (err: any) {
    state.errorMessage = err.response?.data?.detail || '删除文件失败'
    throw err
  }
}

const batchResolve = async (pairIds: number[], action: 'keep_both' | 'ignore') => {
  try {
    await axios.post(`${API_BASE_URL}/dedup/candidates-batch-resolve`, {
      pair_ids: pairIds,
      action,
    })
    await refresh()
  } catch (err: any) {
    state.errorMessage = err.response?.data?.detail || '批量处理失败'
    throw err
  }
}

export const dedupStore = {
  state,
  summary: computed(() => state.summary),
  pairs: computed(() => state.pairs),
  loading: computed(() => state.loading),
  errorMessage: computed(() => state.errorMessage),
  total: computed(() => state.total),
  fetchSummary,
  fetchPairs,
  refresh,
  resolvePair,
  recheckMedia,
  deleteMediaFile,
  batchResolve,
  setFilters(filters: { level?: DedupState['filterLevel']; status?: DedupState['filterStatus']; mediaType?: DedupState['filterMediaType']; sort?: DedupState['sort'] }) {
    if (filters.level !== undefined) state.filterLevel = filters.level
    if (filters.status !== undefined) state.filterStatus = filters.status
    if (filters.mediaType !== undefined) state.filterMediaType = filters.mediaType
    if (filters.sort !== undefined) state.sort = filters.sort
    state.page = 1
  },
  setPage(page: number) { state.page = Math.max(1, page) },
  clearError() { state.errorMessage = '' },
}
