<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import {
  CheckSquare,
  ChevronRight,
  Download,
  Headphones,
  RefreshCw,
  Search,
  Square,
  X,
} from 'lucide-vue-next'
import PaginationControl from '../PaginationControl.vue'
import { API_BASE_URL, authUrl } from '../../config'
import type { ExternalFavoriteItem, ExternalFavoriteSource, Media } from '../../types'
import { AsyncMediaDetail as MediaDetail } from '../asyncComponents'
import ThemeSelect from '../ThemeSelect.vue'
import { asmrDownloadStore } from '../../stores/asmrDownloadStore'
import { useExternalFavoritesPage } from '../../composables/useExternalFavoritesPage'
import { EmptyState, UiButton, UiIconButton, UiInput, UiModal, UiSkeleton, buttonClass, controlClass, fieldHintClass, fieldLabelClass, type Tone } from '../ui'
import ExternalSourceLayout from './ExternalSourceLayout.vue'
import ExternalItemCard from './ExternalItemCard.vue'
import ExternalPickRow from './ExternalPickRow.vue'

const AUDIO_FORMAT_OPTIONS: { value: 'all' | 'no_wav' | 'mp3_only'; label: string }[] = [
  { value: 'all', label: '全部格式' },
  { value: 'no_wav', label: '跳过 WAV（推荐）' },
  { value: 'mp3_only', label: '仅 MP3' },
]
const AUDIO_VERSION_OPTIONS: { value: 'all' | 'no_se' | 'se_only'; label: string }[] = [
  { value: 'all', label: '全部版本' },
  { value: 'no_se', label: '仅无 SE / 无背景声' },
  { value: 'se_only', label: '仅有 SE / 有背景声' },
]

// P2: sync the user's "喜欢" playlist, download works to the local library as
// media_type="audio", and open downloaded ones in the audio player.

// URL-shaped config (api base, mirror list, playlist URL) is persisted both
// to the backend source row (via persistSourceSettings -> PATCH) and to
// localStorage. The localStorage copy is the fallback when there is no source
// row yet — e.g. first time the user opens the panel, or after they nuked
// the source — so an F5 doesn't wipe what they just typed.
const URLS_KEY = 'he-manager:asmr-urls'
const DEFAULT_API_BASE = 'https://api.asmr-200.com'
const loadStoredUrls = (): { apiBase: string; apiMirrors: string; playlistUrl: string } => {
  try {
    const raw = localStorage.getItem(URLS_KEY)
    if (!raw) return { apiBase: DEFAULT_API_BASE, apiMirrors: '', playlistUrl: '' }
    const data = JSON.parse(raw)
    return {
      apiBase: typeof data?.apiBase === 'string' && data.apiBase ? data.apiBase : DEFAULT_API_BASE,
      apiMirrors: typeof data?.apiMirrors === 'string' ? data.apiMirrors : '',
      playlistUrl: typeof data?.playlistUrl === 'string' ? data.playlistUrl : '',
    }
  } catch {
    return { apiBase: DEFAULT_API_BASE, apiMirrors: '', playlistUrl: '' }
  }
}
const initialUrls = loadStoredUrls()
const apiBase = ref(initialUrls.apiBase)
const apiMirrors = ref(initialUrls.apiMirrors)
interface MirrorPing { base: string; ok: boolean; latency_ms: number | null; error: string | null }
const mirrorPings = ref<MirrorPing[]>([])
const pinging = ref(false)
const playlistUrl = ref(initialUrls.playlistUrl)
const persistUrls = () => {
  try {
    localStorage.setItem(URLS_KEY, JSON.stringify({
      apiBase: apiBase.value,
      apiMirrors: apiMirrors.value,
      playlistUrl: playlistUrl.value,
    }))
  } catch { /* quota / private-mode — ignore */ }
}

// Keep only the username in localStorage. The password travels once to
// /external/asmr/sync to mint a bearer token, then stays out of browser storage.
const CREDENTIALS_KEY = 'he-manager:asmr-credentials'
const loadStoredCredentials = (): { username: string; password: string } => {
  try {
    const raw = localStorage.getItem(CREDENTIALS_KEY)
    if (!raw) return { username: '', password: '' }
    const data = JSON.parse(raw)
    return {
      username: typeof data?.username === 'string' ? data.username : '',
      password: '',
    }
  } catch {
    return { username: '', password: '' }
  }
}
const initialCreds = loadStoredCredentials()
const username = ref(initialCreds.username)
const password = ref(initialCreds.password)
const persistCredentials = () => {
  try {
    localStorage.setItem(CREDENTIALS_KEY, JSON.stringify({
      username: username.value,
    }))
  } catch { /* quota / private-mode — ignore */ }
}
const clearStoredCredentials = () => {
  username.value = ''
  password.value = ''
  try { localStorage.removeItem(CREDENTIALS_KEY) } catch { /* ignore */ }
}
const pageLimit = ref(5)
const audioFormatFilter = ref<'all' | 'no_wav' | 'mp3_only'>('all')
const audioVersionFilter = ref<'all' | 'no_se' | 'se_only'>('all')
const downloadRootPath = ref('')
const searchQuery = ref('')
const syncing = ref(false)
const errorMessage = ref('')
const sources = ref<ExternalFavoriteSource[]>([])
const activeSourceId = ref<number | null>(null)
const sourcesLoaded = ref(false)
const downloadPanelOpen = ref(false)
const downloadButtonRef = ref<HTMLButtonElement | null>(null)
const downloadCloseButtonRef = ref<HTMLButtonElement | null>(null)
const openDownloadPanel = () => { downloadPanelOpen.value = true }
const closeDownloadPanel = () => { downloadPanelOpen.value = false }
const onDownloadKeydown = (event: KeyboardEvent) => {
  if (downloadPanelOpen.value && event.key === 'Escape') closeDownloadPanel()
}
watch(downloadPanelOpen, async open => {
  await nextTick()
  if (open) downloadCloseButtonRef.value?.focus()
  else downloadButtonRef.value?.focus()
})
const selectedDownloadIds = ref<Set<number>>(new Set())
const {
  items,
  totalItems,
  currentPage,
  loading,
  error: favoritesError,
  totalPages,
  pageSize: favoritesPageSize,
  pageStart,
  pageEnd,
  fetchItems,
  setPage: setFavoritesPage,
} = useExternalFavoritesPage({
  sourceType: 'asmr',
  activeSourceId,
  searchQuery,
  onSearchReset: () => { selectedDownloadIds.value = new Set() },
})
const localAudioList = ref<Media[]>([])
const selectedLocalMedia = ref<Media | null>(null)

const settingsStatus = ref<'idle' | 'saving' | 'saved'>('idle')
// True while we're writing form fields FROM a source (initial load / source
// switch / post-sync). The auto-save watcher must ignore those writes so it
// doesn't PATCH the value straight back and fight the load.
let hydrating = false
let saveTimer: ReturnType<typeof setTimeout> | undefined

const downloadJob = asmrDownloadStore.job
const downloadInProgress = asmrDownloadStore.inProgress

const activeSiteSources = computed(() => sources.value.filter(source => source.source_type === 'asmr'))
const activeSource = computed(() =>
  activeSiteSources.value.find(source => source.id === activeSourceId.value) || activeSiteSources.value[0] || null,
)

const filteredItems = computed(() => items.value)
const pagedItems = computed(() => items.value)

const downloadableItems = computed(() => items.value.filter(item => !item.local_media_id))
const selectedDownloadItems = computed(() =>
  items.value.filter(item => selectedDownloadIds.value.has(item.id) && !item.local_media_id),
)
const allDownloadableSelected = computed(() =>
  downloadableItems.value.length > 0 && downloadableItems.value.every(item => selectedDownloadIds.value.has(item.id)),
)

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

const formatTime = (value: string | null) => (value ? new Date(value).toLocaleString() : '-')
const coverSrc = (item: ExternalFavoriteItem) => authUrl(`${API_BASE_URL}/external/favorites/${item.id}/cover`)

const goToPage = (page: number) => {
  const target = Math.min(Math.max(page, 1), totalPages.value)
  if (!setFavoritesPage(target)) return
  selectedDownloadIds.value = new Set()
}

const hydrateFromSource = (s: ExternalFavoriteSource | null | undefined) => {
  if (!s) return
  hydrating = true
  if (s.favorites_url) apiBase.value = s.favorites_url
  apiMirrors.value = s.api_mirrors || ''
  audioFormatFilter.value = (s.audio_format_filter as typeof audioFormatFilter.value) || 'all'
  audioVersionFilter.value = (s.audio_version_filter as typeof audioVersionFilter.value) || 'all'
  playlistUrl.value = s.playlist_url || ''
  downloadRootPath.value = s.download_root_path || ''
  // Watchers flush before nextTick, so hydrating is still true when they run.
  nextTick(() => { hydrating = false })
}

// Persist the format / SE-version / playlist-URL prefs on change, no button
// and no full re-sync. Debounced so typing in the playlist field doesn't
// PATCH on every keystroke.
const persistSourceSettings = () => {
  if (hydrating || !activeSourceId.value) return
  if (saveTimer) clearTimeout(saveTimer)
  settingsStatus.value = 'saving'
  saveTimer = setTimeout(async () => {
    try {
      const res = await axios.patch(`${API_BASE_URL}/external/sources/${activeSourceId.value}`, {
        audio_format_filter: audioFormatFilter.value,
        audio_version_filter: audioVersionFilter.value,
        playlist_url: playlistUrl.value.trim() || null,
      })
      const updated = res.data as ExternalFavoriteSource
      sources.value = sources.value.map(s => (s.id === updated.id ? updated : s))
      settingsStatus.value = 'saved'
      setTimeout(() => { if (settingsStatus.value === 'saved') settingsStatus.value = 'idle' }, 2000)
    } catch (err: any) {
      settingsStatus.value = 'idle'
      errorMessage.value = err.response?.data?.detail || '保存设置失败'
    }
  }, 600)
}

const fetchSources = async () => {
  const res = await axios.get(`${API_BASE_URL}/external/sources`)
  sources.value = res.data
  sourcesLoaded.value = true
  if (!activeSourceId.value && activeSiteSources.value.length > 0) {
    const first = activeSiteSources.value[0]
    activeSourceId.value = first.id
    hydrateFromSource(first)
  }
}

const pingMirrors = async () => {
  pinging.value = true
  mirrorPings.value = []
  try {
    const res = await axios.post(`${API_BASE_URL}/external/asmr/mirrors/ping`, {
      api_base: apiBase.value.trim() || undefined,
      api_mirrors: apiMirrors.value.trim() || undefined,
    })
    mirrorPings.value = res.data.results || []
  } catch (err) {
    console.error('Failed to ping ASMR mirrors:', err)
    errorMessage.value = '镜像探活失败'
  } finally {
    pinging.value = false
  }
}

const fetchLocalAudioList = async () => {
  const res = await axios.get(`${API_BASE_URL}/media`, { params: { media_type: 'audio' } })
  localAudioList.value = res.data
  return localAudioList.value
}

const syncAsmr = async () => {
  if (!playlistUrl.value.trim() || !username.value.trim() || !password.value) {
    errorMessage.value = '请填写「喜欢」播放列表地址 + 你本人的 asmr.one 账号密码'
    return
  }
  syncing.value = true
  errorMessage.value = ''
  try {
    const res = await axios.post(`${API_BASE_URL}/external/asmr/sync`, {
      source_id: activeSourceId.value || undefined,
      name: 'ASMR',
      api_base: apiBase.value.trim(),
      api_mirrors: apiMirrors.value.trim() || undefined,
      audio_format_filter: audioFormatFilter.value,
      audio_version_filter: audioVersionFilter.value,
      playlist_url: playlistUrl.value.trim() || undefined,
      username: username.value.trim() || undefined,
      password: password.value || undefined,
      page_limit: pageLimit.value,
    })
    const source = res.data.source as ExternalFavoriteSource
    activeSourceId.value = source.id
    hydrateFromSource(source)
    password.value = ''
    persistCredentials()
    await fetchSources()
    await fetchItems(true)
  } catch (err: any) {
    console.error('Failed to sync ASMR favorites:', err)
    errorMessage.value = err.response?.data?.detail || '同步 ASMR 收藏失败'
  } finally {
    syncing.value = false
  }
}

const selectSource = async (source: ExternalFavoriteSource) => {
  activeSourceId.value = source.id
  hydrateFromSource(source)
  selectedDownloadIds.value = new Set()
  await fetchItems(true)
}

const saveDownloadRootPath = async () => {
  if (!activeSourceId.value) return true
  const trimmed = downloadRootPath.value.trim()
  if (!trimmed) {
    errorMessage.value = '请先设置下载位置'
    return false
  }
  try {
    const res = await axios.patch(`${API_BASE_URL}/external/sources/${activeSourceId.value}`, {
      download_root_path: trimmed,
    })
    const updated = res.data as ExternalFavoriteSource
    sources.value = sources.value.map(s => (s.id === updated.id ? updated : s))
    downloadRootPath.value = updated.download_root_path || ''
    return true
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || '保存路径失败'
    return false
  }
}

const toggleSelect = (item: ExternalFavoriteItem) => {
  if (item.local_media_id) return
  const next = new Set(selectedDownloadIds.value)
  next.has(item.id) ? next.delete(item.id) : next.add(item.id)
  selectedDownloadIds.value = next
}

const toggleSelectAll = () => {
  const next = new Set(selectedDownloadIds.value)
  if (allDownloadableSelected.value) downloadableItems.value.forEach(i => next.delete(i.id))
  else downloadableItems.value.forEach(i => next.add(i.id))
  selectedDownloadIds.value = next
}

const startDownload = async () => {
  if (selectedDownloadItems.value.length === 0 || downloadInProgress.value) return
  if (!downloadRootPath.value.trim()) {
    openDownloadPanel()
    errorMessage.value = '请先设置下载位置'
    return
  }
  errorMessage.value = ''
  asmrDownloadStore.clearError()
  if (!(await saveDownloadRootPath())) return
  try {
    await asmrDownloadStore.startDownload(
      selectedDownloadItems.value.map(i => i.id),
      downloadRootPath.value.trim(),
    )
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || '启动下载失败'
  }
}

const openLocalMedia = async (mediaId: number) => {
  let media = localAudioList.value.find(m => m.id === mediaId)
  if (!media) {
    const list = await fetchLocalAudioList()
    media = list.find(m => m.id === mediaId)
  }
  if (!media) {
    const res = await axios.get(`${API_BASE_URL}/media/${mediaId}`)
    media = res.data as Media
    localAudioList.value = [media, ...localAudioList.value.filter(m => m.id !== mediaId)]
  }
  if (media) selectedLocalMedia.value = media
}

const openItem = async (item: ExternalFavoriteItem) => {
  if (item.local_media_id) {
    try {
      await openLocalMedia(item.local_media_id)
      return
    } catch (err) {
      console.error('Failed to open local audio:', err)
    }
  }
  window.open(item.url, '_blank', 'noreferrer')
}

const updateLocalMediaInList = (media: Media) => {
  const idx = localAudioList.value.findIndex(m => m.id === media.id)
  if (idx >= 0) localAudioList.value[idx] = media
  else localAudioList.value = [media, ...localAudioList.value]
  selectedLocalMedia.value = media
}

let unsubscribeCompleted: (() => void) | null = null

onMounted(async () => {
  asmrDownloadStore.ensureResumed()
  window.addEventListener('keydown', onDownloadKeydown)
  unsubscribeCompleted = asmrDownloadStore.onCompleted(async () => {
    await fetchItems()
    await fetchLocalAudioList()
  })
  await fetchSources()
  await fetchItems()
})

onUnmounted(() => {
  window.removeEventListener('keydown', onDownloadKeydown)
  if (unsubscribeCompleted) { unsubscribeCompleted(); unsubscribeCompleted = null }
  if (saveTimer) clearTimeout(saveTimer)
})

watch([audioFormatFilter, audioVersionFilter, playlistUrl], persistSourceSettings)
// Mirror the URL-shaped fields into localStorage on every change. No
// hydrating guard here — when hydrateFromSource() pulls values from the
// freshly synced source row, we *want* localStorage to track that copy.
watch([apiBase, apiMirrors, playlistUrl], persistUrls)
watch(username, persistCredentials)
watch(() => asmrDownloadStore.errorMessage.value, msg => { if (msg) errorMessage.value = msg })
watch(favoritesError, message => { errorMessage.value = message })
</script>

<template>
  <ExternalSourceLayout
    :status="statusText"
    :status-tone="statusTone"
    :meta="activeSource?.last_synced_at ? `上次同步 ${formatTime(activeSource.last_synced_at)}` : '尚未同步喜欢列表'"
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
        <span :class="fieldLabelClass">「喜欢」播放列表地址</span>
        <UiInput v-model="playlistUrl" placeholder="https://asmr.one/playlist?id=xxxxxxxx-xxxx-…" />
        <span :class="fieldHintClass">该列表对外不可见，需要你本人的账号令牌才能读取。改动后自动保存。</span>
      </label>

      <div class="grid grid-cols-2 gap-3">
        <label class="block min-w-0">
          <span :class="fieldLabelClass">账号 <span class="text-danger">*</span></span>
          <UiInput v-model="username" autocomplete="off" placeholder="用户名" />
        </label>
        <label class="block min-w-0">
          <span :class="fieldLabelClass">密码 <span class="text-danger">*</span></span>
          <UiInput v-model="password" type="password" autocomplete="off" placeholder="密码" />
        </label>
      </div>
      <div class="-mt-3 flex items-start justify-between gap-3">
        <p :class="[fieldHintClass, 'mt-0']">
          {{ username ? '已记住用户名，密码不会保存在浏览器' : '密码只用于本次换取令牌，不会保存在浏览器或后端' }}
        </p>
        <button
          v-if="username || password"
          type="button"
          class="shrink-0 rounded-md px-1 text-caption font-medium text-subtle transition-colors hover:text-danger focus-ring"
          @click="clearStoredCredentials"
        >
          清除已保存
        </button>
      </div>

      <div class="grid grid-cols-[96px_minmax(0,1fr)] gap-3">
        <label class="block min-w-0">
          <span :class="fieldLabelClass">同步页数</span>
          <UiInput v-model.number="pageLimit" type="number" min="1" max="50" />
        </label>
        <label class="block min-w-0">
          <span :class="fieldLabelClass">下载位置</span>
          <UiInput v-model="downloadRootPath" placeholder="例如 /data/downloads" />
        </label>
      </div>

      <label class="block">
        <span :class="fieldLabelClass">下载格式</span>
        <ThemeSelect v-model="audioFormatFilter" :options="AUDIO_FORMAT_OPTIONS" />
        <span :class="fieldHintClass">单作品 WAV 可达数 GB</span>
      </label>

      <label class="block">
        <span :class="fieldLabelClass">SE 版本</span>
        <ThemeSelect v-model="audioVersionFilter" :options="AUDIO_VERSION_OPTIONS" />
        <span :class="fieldHintClass">按文件夹名判断是否带音效 / 背景声</span>
      </label>

      <details class="group rounded-lg border border-line bg-surface-2">
        <summary class="flex h-10 cursor-pointer list-none items-center gap-2 rounded-lg px-3 text-meta font-medium text-muted transition-colors hover:text-ink focus-ring-inset [&::-webkit-details-marker]:hidden">
          <ChevronRight :size="15" class="shrink-0 transition-transform duration-150 group-open:rotate-90" aria-hidden="true" />
          API 与镜像
          <span class="ml-auto truncate text-caption font-normal text-subtle">{{ apiBase }}</span>
        </summary>
        <div class="space-y-4 border-t border-line p-3">
          <label class="block">
            <span :class="fieldLabelClass">API 地址</span>
            <UiInput v-model="apiBase" type="url" placeholder="https://api.asmr-200.com" />
            <span :class="fieldHintClass">镜像被封时会自动回退到其它镜像</span>
          </label>
          <div>
            <div class="mb-1.5 flex items-center justify-between gap-2">
              <label for="asmr-mirrors" class="text-meta font-medium text-muted">镜像列表</label>
              <UiButton size="sm" variant="ghost" :loading="pinging" @click="pingMirrors">{{ pinging ? '探活中…' : '探活' }}</UiButton>
            </div>
            <textarea
              id="asmr-mirrors"
              v-model="apiMirrors"
              rows="3"
              spellcheck="false"
              placeholder="https://api.asmr-200.com&#10;https://api.asmr.one&#10;https://api.asmr-100.com"
              :class="[controlClass('md'), 'h-auto min-h-24 resize-y py-2 font-mono leading-relaxed']"
            ></textarea>
            <p :class="fieldHintClass">每行一个，留空使用内置默认</p>
            <ul v-if="mirrorPings.length" class="mt-2 space-y-1">
              <li v-for="p in mirrorPings" :key="p.base" class="flex items-center gap-2 text-caption">
                <span class="size-1.5 shrink-0 rounded-full" :class="p.ok ? 'bg-success' : 'bg-danger'" aria-hidden="true"></span>
                <span class="min-w-0 flex-1 truncate font-mono text-muted">{{ p.base }}</span>
                <span v-if="p.ok" class="shrink-0 text-subtle tabular-nums">{{ p.latency_ms }} ms</span>
                <span v-else class="shrink-0 text-danger">连不上</span>
              </li>
            </ul>
          </div>
        </div>
      </details>

      <div class="space-y-2">
        <UiButton variant="primary" size="lg" block :loading="syncing" @click="syncAsmr">
          <template #icon><RefreshCw :size="16" aria-hidden="true" /></template>
          {{ syncing ? '同步中' : '同步收藏' }}
        </UiButton>
        <p class="text-center text-caption" aria-live="polite">
          <span v-if="settingsStatus === 'saving'" class="text-subtle">保存中…</span>
          <span v-else-if="settingsStatus === 'saved'" class="text-success">已自动保存</span>
          <span v-else class="text-subtle">音频下载到「下载位置」下的 audio 目录，下完即可在库内播放</span>
        </p>
      </div>

      <p v-if="activeSource?.last_error" role="alert" class="rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">
        {{ activeSource.last_error }}
      </p>
    </template>

    <div class="flex items-center gap-2">
      <p class="hidden shrink-0 pr-2 text-meta text-subtle tabular-nums sm:block">{{ totalItems }} 部</p>
      <UiInput v-model="searchQuery" type="search" placeholder="搜索标题或社团" aria-label="搜索作品标题或社团" class="flex-1">
        <template #leading><Search :size="16" /></template>
      </UiInput>
      <UiIconButton label="刷新列表" variant="secondary" @click="fetchItems()"><RefreshCw :size="16" aria-hidden="true" /></UiIconButton>
      <button ref="downloadButtonRef" type="button" :class="buttonClass('primary', 'md')" title="下载选择" @click="openDownloadPanel">
        <Download :size="16" aria-hidden="true" />
        下载
        <span v-if="selectedDownloadItems.length > 0" class="tabular-nums">{{ selectedDownloadItems.length }}</span>
      </button>
    </div>

    <div v-if="downloadInProgress && downloadJob" class="space-y-2 rounded-2xl border border-line bg-surface p-4">
      <div class="flex items-center justify-between gap-3 text-meta">
        <span class="min-w-0 truncate text-muted">下载中：<span class="font-medium text-ink">{{ downloadJob.current_book_title || '准备中' }}</span></span>
        <span class="shrink-0 text-subtle tabular-nums">{{ asmrDownloadStore.downloadedTracks.value }} / {{ asmrDownloadStore.totalTracks.value }} 轨</span>
      </div>
      <div class="h-1 overflow-hidden rounded-sm bg-surface-3" role="progressbar" :aria-valuenow="asmrDownloadStore.progressPercent.value" aria-valuemin="0" aria-valuemax="100" aria-label="下载进度">
        <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: `${asmrDownloadStore.progressPercent.value}%` }"></div>
      </div>
      <UiButton
        v-if="asmrDownloadStore.canCancel.value"
        size="sm"
        variant="ghost"
        class="-ml-2 hover:!bg-danger/12 hover:!text-danger"
        @click="asmrDownloadStore.cancelDownload()"
      >
        <template #icon><X :size="14" aria-hidden="true" /></template>
        取消下载
      </UiButton>
    </div>

    <p v-if="errorMessage" role="alert" class="rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">
      {{ errorMessage }}
    </p>

    <div v-if="loading" class="poster-grid pt-2" aria-busy="true">
      <div v-for="i in 8" :key="i">
        <UiSkeleton class="aspect-square w-full rounded-2xl" />
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
          :meta="item.category_name || 'asmr.one'"
          :code="item.external_id"
          :downloaded="!!item.local_media_id"
          aspect="1 / 1"
          :placeholder-icon="Headphones"
          @click="openItem(item)"
        />
      </div>

      <div class="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
        <span class="text-meta text-subtle tabular-nums">{{ pageStart }}–{{ pageEnd }} / {{ totalItems }} 部</span>
        <PaginationControl
          v-if="totalPages > 1"
          :page="currentPage"
          :page-count="totalPages"
          :total-items="totalItems"
          :page-size="favoritesPageSize"
          :disabled="loading"
          item-label="条 ASMR"
          @change="goToPage"
        />
      </div>
    </template>

    <div v-else class="rounded-2xl border border-dashed border-line">
      <EmptyState :icon="Headphones" title="还没有 ASMR 收藏" description="填好播放列表地址和账号后点「同步收藏」。" />
    </div>

    <UiModal
      v-model:open="downloadPanelOpen"
      title="选择下载作品"
      :description="`当前列表 ${filteredItems.length} 个作品，已选 ${selectedDownloadItems.length} 个`"
      placement="right"
    >
      <div class="space-y-4">
        <label class="block">
          <span :class="fieldLabelClass">下载位置 <span class="text-danger">*</span></span>
          <UiInput v-model="downloadRootPath" required placeholder="例如 D:\HE\downloads 或 /data/downloads" />
          <span :class="fieldHintClass">音频保存到该路径下的 audio 目录，单作品可能数百 MB 到数 GB。</span>
        </label>

        <div class="flex flex-wrap items-center gap-2">
          <UiButton size="sm" :disabled="downloadableItems.length === 0" @click="toggleSelectAll">
            <template #icon>
              <CheckSquare v-if="allDownloadableSelected" :size="14" aria-hidden="true" />
              <Square v-else :size="14" aria-hidden="true" />
            </template>
            全选未下载
          </UiButton>
          <UiButton size="sm" variant="ghost" :disabled="selectedDownloadItems.length === 0" @click="selectedDownloadIds = new Set()">清空选择</UiButton>
        </div>

        <div v-if="(downloadInProgress && downloadJob) || downloadJob?.results?.length" class="space-y-3 rounded-2xl border border-line bg-surface p-4">
          <template v-if="downloadInProgress && downloadJob">
            <div class="flex items-center justify-between gap-3 text-meta">
              <span class="min-w-0 truncate font-medium text-ink">{{ downloadJob.current_book_title || '准备中' }}</span>
              <span class="shrink-0 text-subtle tabular-nums">{{ asmrDownloadStore.downloadedTracks.value }} / {{ asmrDownloadStore.totalTracks.value }} 轨 · {{ asmrDownloadStore.progressPercent.value }}%</span>
            </div>
            <div class="h-1 overflow-hidden rounded-sm bg-surface-3">
              <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: `${asmrDownloadStore.progressPercent.value}%` }"></div>
            </div>
          </template>
          <ul v-if="downloadJob?.results?.length" class="max-h-28 space-y-1 overflow-y-auto" :class="downloadInProgress ? 'border-t border-line pt-3' : ''">
            <li
              v-for="result in downloadJob.results.slice(-5)"
              :key="`${result.item_id}-${result.status}`"
              class="flex min-w-0 items-center gap-2 text-caption"
            >
              <span class="w-12 shrink-0 font-medium" :class="result.status === 'completed' ? 'text-success' : result.status === 'canceled' ? 'text-warning' : 'text-danger'">
                {{ result.status === 'completed' ? '完成' : result.status === 'canceled' ? '已取消' : '失败' }}
              </span>
              <span class="min-w-0 truncate text-muted">{{ result.title || result.item_id }}{{ result.error ? ` · ${result.error}` : '' }}</span>
            </li>
          </ul>
        </div>

        <div class="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
          <ExternalPickRow
            v-for="item in filteredItems"
            :key="item.id"
            :title="item.title"
            :meta="`${item.external_id} · ${item.category_name || 'asmr.one'}`"
            :cover="item.cover_url ? coverSrc(item) : null"
            :url="item.url"
            :checked="selectedDownloadIds.has(item.id)"
            :downloaded="!!item.local_media_id"
            square
            :placeholder-icon="Headphones"
            @toggle="toggleSelect(item)"
          />
        </div>
      </div>

      <template #footer>
        <p class="mr-auto text-meta text-subtle">
          <span class="font-medium text-ink tabular-nums">{{ selectedDownloadItems.length }}</span> 个作品待下载
          <span v-if="!downloadRootPath.trim()" class="block text-warning">请先填写下载位置</span>
        </p>
        <UiButton
          variant="primary"
          :disabled="selectedDownloadItems.length === 0 || !downloadRootPath.trim()"
          :loading="downloadInProgress"
          @click="startDownload"
        >
          <template #icon><Download :size="16" aria-hidden="true" /></template>
          {{ downloadInProgress ? '下载中' : '开始下载' }}
        </UiButton>
      </template>
    </UiModal>

    <MediaDetail
      v-if="selectedLocalMedia"
      :initial-media="selectedLocalMedia"
      :all-media="localAudioList"
      @close="selectedLocalMedia = null"
      @updated="updateLocalMediaInList"
      @navigate="selectedLocalMedia = $event"
    />
  </ExternalSourceLayout>
</template>
