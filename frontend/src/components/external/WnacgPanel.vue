<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import {
  BookOpen,
  CheckSquare,
  Download,
  RefreshCw,
  Search,
  ShieldCheck,
  Square,
  X,
} from 'lucide-vue-next'
import { API_BASE_URL, authUrl } from '../../config'
import type { ExternalFavoriteItem, ExternalFavoriteSource, Media } from '../../types'
import { AsyncMediaDetail as MediaDetail } from '../asyncComponents'
import ExternalDownloadProgress from '../ExternalDownloadProgress.vue'
import AutoSyncSection from './AutoSyncSection.vue'
import PaginationControl from '../PaginationControl.vue'
import { externalDownloadStore } from '../../stores/externalDownloadStore'
import { useExternalFavoritesPage } from '../../composables/useExternalFavoritesPage'
import { EmptyState, UiButton, UiIconButton, UiInput, UiModal, UiSkeleton, controlClass, fieldHintClass, fieldLabelClass, type Tone } from '../ui'
import ExternalSourceLayout from './ExternalSourceLayout.vue'
import ExternalItemCard from './ExternalItemCard.vue'
import ExternalPickRow from './ExternalPickRow.vue'

const favoritesUrl = ref('https://www.wnacg.com/users-users_fav.html')
const downloadRootPath = ref('')
const cookie = ref('')
const pageLimit = ref(30)
const searchQuery = ref('')
const syncing = ref(false)
const errorMessage = ref('')
const sources = ref<ExternalFavoriteSource[]>([])
const activeSourceId = ref<number | null>(null)
const sourcesLoaded = ref(false)
const downloadPanelOpen = ref(false)
const selectedDownloadIds = ref<Set<number>>(new Set())
const {
  items,
  totalItems,
  currentPage,
  loading,
  error: favoritesError,
  totalPages,
  pageSize: favoritesPageSize,
  fetchItems,
  setPage: setFavoritesPage,
} = useExternalFavoritesPage({
  sourceType: 'wnacg',
  activeSourceId,
  searchQuery,
  onSearchReset: () => { selectedDownloadIds.value = new Set() },
})
const downloadJob = externalDownloadStore.job
const downloadInProgress = externalDownloadStore.inProgress
const failedTasks = externalDownloadStore.failedTasks
const localMangaList = ref<Media[]>([])
const selectedLocalMedia = ref<Media | null>(null)

const activeSiteSources = computed(() => sources.value.filter(source => source.source_type === 'wnacg'))
const activeSource = computed(() => {
  return activeSiteSources.value.find(source => source.id === activeSourceId.value) || activeSiteSources.value[0] || null
})

const filteredItems = computed(() => items.value)
const pagedItems = computed(() => items.value)
const downloadableFilteredItems = computed(() => items.value.filter(item => !item.local_media_id))
const selectedDownloadItems = computed(() => {
  return items.value.filter(item => selectedDownloadIds.value.has(item.id) && !item.local_media_id)
})
const allFilteredSelected = computed(() => {
  return downloadableFilteredItems.value.length > 0 && downloadableFilteredItems.value.every(item => selectedDownloadIds.value.has(item.id))
})

const statusText = computed(() => {
  if (!activeSource.value) return '未同步'
  if (activeSource.value.status === 'ok') return '已同步'
  if (activeSource.value.status === 'syncing') return '同步中'
  if (activeSource.value.status === 'error') return '同步失败'
  return '待同步'
})

const statusTone = computed<Tone>(() => {
  const status = activeSource.value?.status
  if (status === 'ok') return 'success'
  if (status === 'syncing') return 'info'
  if (status === 'error') return 'danger'
  return 'neutral'
})

const formatTime = (value: string | null) => {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

const coverSrc = (item: ExternalFavoriteItem) => {
  return authUrl(`${API_BASE_URL}/external/favorites/${item.id}/cover`)
}

const fetchLocalMangaList = async () => {
  const res = await axios.get(`${API_BASE_URL}/media`, { params: { media_type: 'manga' } })
  localMangaList.value = res.data
  return localMangaList.value
}

const openLocalMedia = async (mediaId: number) => {
  let media = localMangaList.value.find(item => item.id === mediaId)
  if (!media) {
    const mediaList = await fetchLocalMangaList()
    media = mediaList.find(item => item.id === mediaId)
  }
  if (!media) {
    const res = await axios.get(`${API_BASE_URL}/media/${mediaId}`)
    media = res.data as Media
    localMangaList.value = [media, ...localMangaList.value.filter(item => item.id !== mediaId)]
  }
  if (media) selectedLocalMedia.value = media
}

const openExternalItem = async (item: ExternalFavoriteItem) => {
  if (item.local_media_id) {
    try {
      await openLocalMedia(item.local_media_id)
      return
    } catch (err) {
      console.error('Failed to open local manga:', err)
    }
  }
  window.open(item.url, '_blank', 'noreferrer')
}

const closeLocalMedia = () => {
  selectedLocalMedia.value = null
}

const updateLocalMediaInList = (media: Media) => {
  const index = localMangaList.value.findIndex(item => item.id === media.id)
  if (index >= 0) {
    localMangaList.value[index] = media
  } else {
    localMangaList.value = [media, ...localMangaList.value]
  }
  selectedLocalMedia.value = media
}

const goToPage = (page: number) => {
  const target = Math.min(Math.max(page, 1), totalPages.value)
  if (!setFavoritesPage(target)) return
  selectedDownloadIds.value = new Set()
}

const toggleDownloadSelection = (item: ExternalFavoriteItem) => {
  if (item.local_media_id) return
  const next = new Set(selectedDownloadIds.value)
  if (next.has(item.id)) {
    next.delete(item.id)
  } else {
    next.add(item.id)
  }
  selectedDownloadIds.value = next
}

const toggleAllFilteredSelection = () => {
  const next = new Set(selectedDownloadIds.value)
  if (allFilteredSelected.value) {
    downloadableFilteredItems.value.forEach(item => next.delete(item.id))
  } else {
    downloadableFilteredItems.value.forEach(item => next.add(item.id))
  }
  selectedDownloadIds.value = next
}

const clearDownloadSelection = () => {
  selectedDownloadIds.value = new Set()
}

const exportSelectedLinks = () => {
  if (selectedDownloadItems.value.length === 0) return
  const content = selectedDownloadItems.value.map(item => `${item.title}\n${item.url}`).join('\n\n')
  const blob = new Blob([content], { type: 'text/plain;charset=utf-8' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = `he-manager-external-downloads-${new Date().toISOString().slice(0, 10)}.txt`
  link.click()
  URL.revokeObjectURL(url)
}

const startWnacgDownload = async () => {
  if (selectedDownloadItems.value.length === 0 || downloadInProgress.value) return
  const pendingItems = selectedDownloadItems.value.filter(item => !item.local_media_id)
  if (pendingItems.length === 0) return
  const trimmedDownloadRootPath = downloadRootPath.value.trim()
  if (!trimmedDownloadRootPath) {
    downloadPanelOpen.value = true
    errorMessage.value = '请先设置下载位置'
    return
  }
  errorMessage.value = ''
  externalDownloadStore.clearError()
  const saved = await saveDownloadRootPath()
  if (!saved) return
  try {
    await externalDownloadStore.startDownload(
      pendingItems.map(item => item.id),
      trimmedDownloadRootPath,
    )
  } catch (err: any) {
    console.error('Failed to start WNACG download:', err)
    errorMessage.value = err.response?.data?.detail || '启动下载失败'
  }
}

const retryFailedDownloads = async () => {
  if (downloadInProgress.value) return
  const trimmedDownloadRootPath = downloadRootPath.value.trim()
  if (!trimmedDownloadRootPath) {
    errorMessage.value = '请先设置下载位置'
    return
  }
  errorMessage.value = ''
  externalDownloadStore.clearError()
  const saved = await saveDownloadRootPath()
  if (!saved) return
  try {
    await externalDownloadStore.retryFailed(trimmedDownloadRootPath)
  } catch (err: any) {
    console.error('Failed to retry WNACG downloads:', err)
    errorMessage.value = err.response?.data?.detail || '重试失败'
  }
}

const dismissDownloadJob = () => externalDownloadStore.dismissJob()

const fetchSources = async () => {
  const res = await axios.get(`${API_BASE_URL}/external/sources`)
  sources.value = res.data
  sourcesLoaded.value = true
  if (!activeSourceId.value && activeSiteSources.value.length > 0) {
    activeSourceId.value = activeSiteSources.value[0].id
    favoritesUrl.value = activeSiteSources.value[0].favorites_url
    downloadRootPath.value = activeSiteSources.value[0].download_root_path || ''
  }
}

const syncWnacg = async () => {
  syncing.value = true
  errorMessage.value = ''
  try {
    const res = await axios.post(`${API_BASE_URL}/external/wnacg/sync`, {
      source_id: activeSourceId.value || undefined,
      name: 'WNACG',
      favorites_url: favoritesUrl.value.trim(),
      cookie: cookie.value.trim() || undefined,
      page_limit: pageLimit.value,
    })
    const source = res.data.source as ExternalFavoriteSource
    activeSourceId.value = source.id
    cookie.value = ''
    await fetchSources()
    await fetchItems(true)
  } catch (err: any) {
    console.error('Failed to sync WNACG favorites:', err)
    errorMessage.value = err.response?.data?.detail || '同步 WNACG 收藏失败'
  } finally {
    syncing.value = false
  }
}

const selectSource = async (source: ExternalFavoriteSource) => {
  activeSourceId.value = source.id
  favoritesUrl.value = source.favorites_url
  downloadRootPath.value = source.download_root_path || ''
  selectedDownloadIds.value = new Set()
  await fetchItems(true)
}

const saveDownloadRootPath = async () => {
  if (!activeSourceId.value) return true
  const trimmedDownloadRootPath = downloadRootPath.value.trim()
  if (!trimmedDownloadRootPath) {
    errorMessage.value = '请先设置下载位置'
    return false
  }
  errorMessage.value = ''
  try {
    const res = await axios.patch(`${API_BASE_URL}/external/sources/${activeSourceId.value}`, {
      download_root_path: trimmedDownloadRootPath,
    })
    const updated = res.data as ExternalFavoriteSource
    sources.value = sources.value.map(source => source.id === updated.id ? updated : source)
    downloadRootPath.value = updated.download_root_path || ''
    return true
  } catch (err: any) {
    console.error('Failed to save download path:', err)
    errorMessage.value = err.response?.data?.detail || '保存路径失败'
    return false
  }
}

const handleAutoSyncUpdate = async (payload: { auto_sync_enabled?: boolean; auto_sync_interval_hours?: number }) => {
  if (!activeSourceId.value) return
  try {
    const res = await axios.patch(`${API_BASE_URL}/auto-sync/wnacg/${activeSourceId.value}`, payload)
    const updated = res.data as ExternalFavoriteSource
    sources.value = sources.value.map(s => s.id === updated.id ? updated : s)
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || '更新自动同步配置失败'
  }
}

let unsubscribeCompleted: (() => void) | null = null

onMounted(async () => {
  externalDownloadStore.ensureResumed()
  unsubscribeCompleted = externalDownloadStore.onCompleted(async () => {
    await fetchItems()
    await fetchLocalMangaList()
  })
  await fetchSources()
  await fetchItems()
})

onUnmounted(() => {
  if (unsubscribeCompleted) {
    unsubscribeCompleted()
    unsubscribeCompleted = null
  }
})

watch(() => externalDownloadStore.errorMessage.value, (msg) => {
  if (msg) errorMessage.value = msg
})
watch(favoritesError, message => {
  errorMessage.value = message
})
</script>

<template>
  <ExternalSourceLayout
    :status="statusText"
    :status-tone="statusTone"
    :meta="activeSource?.last_synced_at ? `上次同步 ${formatTime(activeSource.last_synced_at)}` : '尚未同步收藏夹'"
    :default-open="sourcesLoaded && !activeSource"
  >
    <template #config>
      <div v-if="activeSiteSources.length > 0" class="flex flex-wrap gap-2">
        <button
          v-for="source in activeSiteSources"
          :key="source.id"
          type="button"
          :aria-pressed="activeSourceId === source.id"
          :class="[
            'inline-flex h-8 items-center rounded-full border px-3 text-meta font-medium transition-colors focus-ring',
            activeSourceId === source.id ? 'border-accent/50 bg-accent/15 text-accent-glow' : 'border-line bg-surface text-muted hover:border-line-strong hover:text-ink',
          ]"
          @click="selectSource(source)"
        >
          {{ source.name }}
        </button>
      </div>

      <label class="block">
        <span :class="fieldLabelClass">喜欢页地址</span>
        <UiInput v-model="favoritesUrl" type="url" />
      </label>

      <label class="block">
        <span :class="fieldLabelClass">Cookie</span>
        <textarea
          v-model="cookie"
          rows="3"
          placeholder="粘贴你自己账号在 WNACG 的 Cookie"
          :class="[controlClass('md'), 'h-auto min-h-24 resize-y py-2 leading-relaxed']"
        ></textarea>
        <span :class="[fieldHintClass, 'flex items-center gap-1.5']">
          <ShieldCheck :size="13" class="shrink-0 text-success" aria-hidden="true" />
          只保存在本机，同步后输入框会清空
        </span>
      </label>

      <label class="block">
        <span :class="fieldLabelClass">每个分类同步页数</span>
        <UiInput v-model.number="pageLimit" type="number" min="1" max="30" class="w-32" />
      </label>

      <UiButton variant="primary" size="lg" block :loading="syncing" @click="syncWnacg">
        <template #icon><RefreshCw :size="16" aria-hidden="true" /></template>
        {{ syncing ? '同步中' : '同步收藏' }}
      </UiButton>

      <p v-if="activeSource?.last_error" role="alert" class="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">
        {{ activeSource.last_error }}
      </p>

      <AutoSyncSection
        v-if="activeSource"
        source-type="wnacg"
        :source-id="activeSource.id"
        :enabled="activeSource.auto_sync_enabled"
        :interval-hours="activeSource.auto_sync_interval_hours"
        :last-run-at="activeSource.auto_sync_last_run_at"
        :next-run-at="activeSource.auto_sync_next_run_at"
        :last-status="activeSource.auto_sync_last_status"
        :last-message="activeSource.auto_sync_last_message"
        :can-enable="!!activeSource.cookie_saved && !!activeSource.download_root_path"
        disable-reason="请先保存 Cookie 并设置下载路径"
        @update="handleAutoSyncUpdate"
      />
    </template>

    <div class="flex items-center gap-2">
      <p class="hidden shrink-0 pr-2 text-meta text-subtle tabular-nums sm:block">{{ totalItems }} 项</p>
      <UiInput v-model="searchQuery" type="search" placeholder="搜索标题或分类" aria-label="搜索收藏标题或分类" class="flex-1">
        <template #leading><Search :size="16" /></template>
      </UiInput>
      <UiIconButton label="刷新列表" variant="secondary" @click="fetchItems()"><RefreshCw :size="16" aria-hidden="true" /></UiIconButton>
      <UiButton variant="primary" title="下载选择" @click="downloadPanelOpen = true">
        <template #icon><Download :size="16" aria-hidden="true" /></template>
        下载
        <template v-if="selectedDownloadItems.length > 0" #trailing>
          <span class="tabular-nums">{{ selectedDownloadItems.length }}</span>
        </template>
      </UiButton>
    </div>

    <p v-if="errorMessage" role="alert" class="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">
      {{ errorMessage }}
    </p>

    <div v-if="loading" class="poster-grid pt-2" aria-busy="true">
      <div v-for="i in 8" :key="i">
        <UiSkeleton class="aspect-[2/3] w-full rounded-2xl" />
        <UiSkeleton shape="text" class="mt-3 w-4/5" />
        <UiSkeleton shape="text" class="mt-2 w-1/2" />
      </div>
    </div>

    <template v-else-if="items.length > 0">
      <div class="poster-grid pt-2">
        <ExternalItemCard
          v-for="item in pagedItems"
          :key="item.id"
          :title="item.title"
          :cover="item.cover_url ? coverSrc(item) : null"
          :meta="item.category_name || 'WNACG'"
          :downloaded="!!item.local_media_id"
          :placeholder-icon="BookOpen"
          @click="openExternalItem(item)"
        />
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <UiButton variant="ghost" size="sm" title="全选当前列表" @click="toggleAllFilteredSelection">
          <template #icon>
            <CheckSquare v-if="allFilteredSelected" :size="14" aria-hidden="true" />
            <Square v-else :size="14" aria-hidden="true" />
          </template>
          全选本页
        </UiButton>
        <PaginationControl
          v-if="totalPages > 1"
          :page="currentPage"
          :page-count="totalPages"
          :total-items="totalItems"
          :page-size="favoritesPageSize"
          :disabled="loading"
          item-label="条收藏"
          @change="goToPage"
        />
      </div>
    </template>

    <div v-else class="rounded-2xl border border-dashed border-line">
      <EmptyState :icon="BookOpen" title="还没有外部收藏" description="填好喜欢页地址和 Cookie 后点「同步收藏」，收藏会显示在这里。" />
    </div>

    <UiModal v-model:open="downloadPanelOpen" title="下载选择" :description="`已选择 ${selectedDownloadItems.length} 个，当前列表 ${filteredItems.length} 个`" placement="right">
      <div class="space-y-4">
        <label class="block">
          <span :class="fieldLabelClass">下载位置 <span class="text-danger">*</span></span>
          <UiInput
            v-model="downloadRootPath"
            required
            placeholder="例如 D:\HE\downloads 或 /data/downloads"
          />
          <span :class="fieldHintClass">必填。漫画会保存到该路径下的 manga 目录，开始下载时会自动记住这个位置。</span>
        </label>

        <div class="flex flex-wrap items-center gap-2">
          <UiButton size="sm" :disabled="downloadableFilteredItems.length === 0" @click="toggleAllFilteredSelection">
            <template #icon>
              <CheckSquare v-if="allFilteredSelected" :size="14" aria-hidden="true" />
              <Square v-else :size="14" aria-hidden="true" />
            </template>
            全选当前列表
          </UiButton>
          <UiButton size="sm" variant="ghost" :disabled="selectedDownloadItems.length === 0" @click="clearDownloadSelection">清空选择</UiButton>
        </div>

        <ExternalDownloadProgress />
        <div
          v-if="downloadJob && !downloadInProgress"
          class="flex flex-wrap items-center gap-2 rounded-lg border px-3.5 py-3"
          :class="failedTasks.length ? 'border-danger/25 bg-danger/10' : 'border-success/25 bg-success/10'"
        >
          <p class="mr-auto text-meta font-medium" :class="failedTasks.length ? 'text-danger' : 'text-success'">
            {{ failedTasks.length ? `${failedTasks.length} 本下载失败（明细见上方列表）` : '本次下载已结束' }}
          </p>
          <UiButton
            v-if="failedTasks.length"
            size="sm"
            :disabled="!downloadRootPath.trim()"
            title="只重新下载失败的漫画，已下好的页会跳过"
            @click="retryFailedDownloads"
          >
            <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
            重试失败项
          </UiButton>
          <UiButton size="sm" variant="ghost" title="关闭进度面板" @click="dismissDownloadJob">
            <template #icon><X :size="14" aria-hidden="true" /></template>
            关闭
          </UiButton>
        </div>

        <div class="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
          <ExternalPickRow
            v-for="item in filteredItems"
            :key="item.id"
            :title="item.title"
            :meta="item.category_name || 'WNACG'"
            :cover="item.cover_url ? coverSrc(item) : null"
            :url="item.url"
            :checked="selectedDownloadIds.has(item.id)"
            :downloaded="!!item.local_media_id"
            :placeholder-icon="BookOpen"
            @toggle="toggleDownloadSelection(item)"
          />
        </div>
      </div>

      <template #footer>
        <UiButton :disabled="selectedDownloadItems.length === 0" @click="exportSelectedLinks">
          <template #icon><Download :size="16" aria-hidden="true" /></template>
          导出所选链接
        </UiButton>
        <UiButton
          variant="primary"
          :disabled="selectedDownloadItems.length === 0 || !downloadRootPath.trim()"
          :loading="downloadInProgress"
          @click="startWnacgDownload"
        >
          <template #icon><Download :size="16" aria-hidden="true" /></template>
          {{ downloadInProgress ? '下载中' : '开始下载' }}
        </UiButton>
      </template>
    </UiModal>

    <MediaDetail
      v-if="selectedLocalMedia"
      :initial-media="selectedLocalMedia"
      :all-media="localMangaList"
      @close="closeLocalMedia"
      @updated="updateLocalMediaInList"
      @navigate="selectedLocalMedia = $event"
    />
  </ExternalSourceLayout>
</template>
