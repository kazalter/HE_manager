<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  ChevronLeft,
  ChevronRight,
  Copy,
  FileImage,
  Film,
  Filter,
  Headphones,
  Layers,
  RefreshCw,
  ShieldCheck,
  Star,
  Trash2,
  X,
} from 'lucide-vue-next'
import { thumbnailUrl } from '../config'
import { dedupStore } from '../stores/dedupStore'
import type { DedupMediaSummary, DuplicateCandidatePair } from '../types'

const summary = dedupStore.summary
const pairs = dedupStore.pairs
const loading = dedupStore.loading
const errorMessage = dedupStore.errorMessage
const total = dedupStore.total

const expandedPairId = ref<number | null>(null)
const selectedPairIds = ref<Set<number>>(new Set())
const processingPairIds = ref<Set<number>>(new Set())
const showFilters = ref(false)
const refreshSpinning = ref(false)
const copiedMediaId = ref<number | null>(null)
const confirmDeletePair = ref<DuplicateCandidatePair | null>(null)
const deleteTrigger = ref<HTMLElement | null>(null)
const modalPanel = ref<HTMLElement | null>(null)
const cancelDeleteButton = ref<HTMLButtonElement | null>(null)

const formatSize = (bytes: number | null) => {
  if (!bytes && bytes !== 0) return '未知'
  if (bytes < 1024) return `${bytes} B`
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`
}

const formatDuration = (seconds: number | null) => {
  if (seconds === null || seconds === undefined) return '未知'
  const h = Math.floor(seconds / 3600)
  const m = Math.floor((seconds % 3600) / 60)
  const s = Math.floor(seconds % 60)
  return h > 0
    ? `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`
    : `${m}:${String(s).padStart(2, '0')}`
}

const mediaMetric = (media: DedupMediaSummary) => {
  if (media.media_type === 'video') return formatDuration(media.duration)
  if (media.media_type === 'manga') return media.page_count ? `${media.page_count} 页` : '页数未知'
  if (media.media_type === 'audio') {
    if (media.page_count) return `${media.page_count} 轨`
    return media.duration ? formatDuration(media.duration) : '时长未知'
  }
  return media.width && media.height ? `${media.width}×${media.height}` : '尺寸未知'
}

const resolution = (media: DedupMediaSummary) => (
  media.width && media.height ? `${media.width}×${media.height}` : '未知'
)

const typeMeta = (type: string) => {
  if (type === 'video') return { label: '视频', icon: Film }
  if (type === 'manga') return { label: '漫画', icon: Layers }
  if (type === 'audio') return { label: '音频', icon: Headphones }
  return { label: '杂图', icon: FileImage }
}

const confidenceMeta = (level: string) => {
  if (level === 'strong_duplicate') {
    return { label: '高置信度', short: '高', cls: 'border-red-400/30 bg-red-400/12 text-red-200' }
  }
  if (level === 'suspected_duplicate') {
    return { label: '中置信度', short: '中', cls: 'border-amber-400/30 bg-amber-400/12 text-amber-200' }
  }
  return { label: '低置信度', short: '低', cls: 'border-sky-400/30 bg-sky-400/12 text-sky-200' }
}

const statusLabel = (status: string) => ({
  pending: '待处理',
  merged: '已保留左侧',
  replaced: '已采用右侧路径',
  kept_both: '已标记非重复',
  ignored: '已忽略',
}[status] || status)

const comparisonRows = (pair: DuplicateCandidatePair) => [
  { label: '标题', left: pair.existing.title, right: pair.candidate.title },
  { label: '路径', left: pair.existing.display_path, right: pair.candidate.display_path },
  { label: '文件大小', left: formatSize(pair.existing.file_size), right: formatSize(pair.candidate.file_size) },
  { label: '分辨率', left: resolution(pair.existing), right: resolution(pair.candidate) },
  { label: pair.existing.media_type === 'manga' ? '页数' : pair.existing.media_type === 'audio' ? '时长/音轨' : '时长', left: mediaMetric(pair.existing), right: mediaMetric(pair.candidate) },
  { label: '收藏', left: pair.existing.favorite ? '已收藏' : '未收藏', right: pair.candidate.favorite ? '已收藏' : '未收藏' },
  { label: '文件状态', left: pair.existing.is_missing ? '文件丢失' : '文件存在', right: pair.candidate.is_missing ? '文件丢失' : '文件存在' },
].map(row => ({ ...row, same: row.left === row.right }))

const deltaSummary = (pair: DuplicateCandidatePair) => {
  const differences = comparisonRows(pair).filter(row => !row.same).map(row => `${row.label}不同`)
  return differences.length ? differences.slice(0, 3) : ['关键属性一致']
}

const evidenceTags = (pair: DuplicateCandidatePair) => {
  const reasons = (pair.reason || '').split('；').map(item => item.trim()).filter(Boolean)
  return reasons.length ? reasons : ['等待更多检测证据']
}

const totalPages = computed(() => Math.max(1, Math.ceil(total.value / dedupStore.state.pageSize)))
const rangeStart = computed(() => total.value ? (dedupStore.state.page - 1) * dedupStore.state.pageSize + 1 : 0)
const rangeEnd = computed(() => Math.min(total.value, dedupStore.state.page * dedupStore.state.pageSize))
const noPairs = computed(() => !loading.value && pairs.value.length === 0)
const selectedCount = computed(() => selectedPairIds.value.size)

watch(pairs, (nextPairs) => {
  const validIds = new Set(nextPairs.map(pair => pair.id))
  selectedPairIds.value = new Set([...selectedPairIds.value].filter(id => validIds.has(id)))
  if (!expandedPairId.value || !validIds.has(expandedPairId.value)) {
    expandedPairId.value = nextPairs[0]?.id ?? null
  }
})

watch(confirmDeletePair, async (pair) => {
  if (!pair) return
  await nextTick()
  cancelDeleteButton.value?.focus()
})

const onFiltersChanged = async () => {
  dedupStore.setFilters({
    level: dedupStore.state.filterLevel,
    status: dedupStore.state.filterStatus,
    mediaType: dedupStore.state.filterMediaType,
    sort: dedupStore.state.sort,
  })
  selectedPairIds.value = new Set()
  await dedupStore.fetchPairs()
}

const goToPage = async (page: number) => {
  if (page < 1 || page > totalPages.value || page === dedupStore.state.page) return
  dedupStore.setPage(page)
  await dedupStore.fetchPairs()
}

const onRefresh = async () => {
  refreshSpinning.value = true
  try {
    await dedupStore.refresh()
  } finally {
    window.setTimeout(() => { refreshSpinning.value = false }, 350)
  }
}

const toggleExpanded = (pairId: number) => {
  expandedPairId.value = expandedPairId.value === pairId ? null : pairId
}

const toggleSelected = (pairId: number) => {
  const next = new Set(selectedPairIds.value)
  if (next.has(pairId)) next.delete(pairId)
  else next.add(pairId)
  selectedPairIds.value = next
}

const clearSelection = () => {
  selectedPairIds.value = new Set()
}

const markProcessing = (pairId: number, active: boolean) => {
  const next = new Set(processingPairIds.value)
  if (active) next.add(pairId)
  else next.delete(pairId)
  processingPairIds.value = next
}

const onResolve = async (
  pair: DuplicateCandidatePair,
  action: 'keep_existing' | 'replace_path' | 'keep_both' | 'ignore',
) => {
  if (processingPairIds.value.has(pair.id)) return
  markProcessing(pair.id, true)
  try {
    await dedupStore.resolvePair(pair.id, action)
    const next = new Set(selectedPairIds.value)
    next.delete(pair.id)
    selectedPairIds.value = next
  } finally {
    markProcessing(pair.id, false)
  }
}

const onBatchNotDuplicate = async () => {
  if (!selectedPairIds.value.size) return
  await dedupStore.batchResolve([...selectedPairIds.value], 'keep_both')
  selectedPairIds.value = new Set()
}

const copyPath = async (media: DedupMediaSummary) => {
  await navigator.clipboard.writeText(media.display_path)
  copiedMediaId.value = media.id
  window.setTimeout(() => {
    if (copiedMediaId.value === media.id) copiedMediaId.value = null
  }, 1200)
}

const askDeleteFile = (pair: DuplicateCandidatePair, event: MouseEvent) => {
  deleteTrigger.value = event.currentTarget as HTMLElement
  confirmDeletePair.value = pair
}

const closeDeleteModal = () => {
  confirmDeletePair.value = null
  nextTick(() => deleteTrigger.value?.focus())
}

const onDeleteConfirmed = async () => {
  if (!confirmDeletePair.value) return
  const pair = confirmDeletePair.value
  try {
    await dedupStore.deleteMediaFile(pair.candidate.id)
    closeDeleteModal()
  } catch {
    // Keep the modal open so the user can read the page-level error and retry/cancel.
  }
}

const onModalKeydown = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    event.preventDefault()
    closeDeleteModal()
    return
  }
  if (event.key !== 'Tab' || !modalPanel.value) return
  const controls = [...modalPanel.value.querySelectorAll<HTMLElement>('button:not([disabled])')]
  if (!controls.length) return
  const first = controls[0]
  const last = controls[controls.length - 1]
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

const handleGlobalEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape' && confirmDeletePair.value) closeDeleteModal()
}

onMounted(async () => {
  window.addEventListener('keydown', handleGlobalEscape)
  await dedupStore.refresh()
})

onBeforeUnmount(() => window.removeEventListener('keydown', handleGlobalEscape))
</script>

<template>
  <div class="relative z-10 min-h-screen">
    <header class="sticky top-0 z-40 border-b border-white/10 bg-background/90 px-6 py-3 backdrop-blur-xl min-[900px]:px-8">
      <div class="flex items-center justify-between gap-4 pl-14 min-[900px]:pl-0">
        <div class="min-w-0">
          <div class="flex items-center gap-3">
            <h1 class="truncate text-2xl font-black tracking-tight text-white">重复管理</h1>
            <span class="hidden rounded-lg border border-accent/25 bg-accent/10 px-2.5 py-1 text-xs font-bold text-accent min-[520px]:inline-flex">
              {{ summary?.pending_pairs ?? 0 }} 待处理
            </span>
          </div>
        </div>
        <button
          type="button"
          @click="onRefresh"
          :disabled="loading"
          class="flex h-11 shrink-0 items-center gap-2 rounded-xl border border-white/12 bg-white/5 px-3.5 text-sm font-bold text-white/75 transition hover:bg-white/10 hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-55"
        >
          <RefreshCw :size="17" :class="(loading || refreshSpinning) ? 'animate-spin' : ''" aria-hidden="true" />
          <span class="hidden min-[480px]:inline">刷新状态</span>
        </button>
      </div>
    </header>

    <main class="space-y-3 px-4 pb-12 pt-3 min-[640px]:px-6 min-[900px]:px-8">
      <div
        v-if="errorMessage"
        role="alert"
        class="flex items-center justify-between gap-3 rounded-xl border border-red-400/25 bg-red-400/10 px-4 py-3 text-sm text-red-100"
      >
        <span>{{ errorMessage }}</span>
        <button type="button" aria-label="关闭错误提示" @click="dedupStore.clearError()" class="rounded-lg p-2 text-white/65 hover:bg-white/10 hover:text-white focus-visible:ring-2 focus-visible:ring-accent">
          <X :size="17" aria-hidden="true" />
        </button>
      </div>

      <section aria-label="重复检测状态" class="flex flex-wrap items-center gap-x-3 gap-y-2 rounded-xl border border-white/10 bg-white/[0.035] px-4 py-2.5 text-sm">
        <span class="font-black text-white">{{ summary?.pending_pairs ?? 0 }} <span class="font-medium text-white/55">待处理</span></span>
        <span class="text-white/20">·</span>
        <span class="font-bold text-red-200">{{ summary?.strong_duplicate ?? 0 }} <span class="font-medium text-white/50">高置信</span></span>
        <span class="text-white/20">·</span>
        <span class="font-bold text-amber-200">{{ summary?.suspected_duplicate ?? 0 }} <span class="font-medium text-white/50">中置信</span></span>
        <span class="text-white/20">·</span>
        <span class="font-bold text-sky-200">{{ summary?.weak_suspected ?? 0 }} <span class="font-medium text-white/50">低置信</span></span>
        <span class="ml-auto flex items-center gap-2 text-white/60">
          <span :class="summary?.worker_running ? 'bg-emerald-300' : 'bg-white/30'" class="h-2 w-2 rounded-full"></span>
          {{ summary?.worker_running ? `检测中 · 队列 ${summary?.queue_size ?? 0}` : '检测任务空闲' }}
        </span>
      </section>

      <section class="rounded-xl border border-white/10 bg-white/[0.035] p-2.5">
        <div class="flex items-center justify-between gap-3">
          <div class="flex min-w-0 items-center gap-2">
            <Filter :size="17" class="text-white/55" aria-hidden="true" />
            <span class="text-sm font-bold text-white">筛选与排序</span>
            <span class="hidden text-xs text-white/45 min-[640px]:inline">当前支持视频、漫画、杂图和音频</span>
          </div>
          <button
            type="button"
            class="flex h-10 items-center gap-1 rounded-lg border border-white/10 bg-white/5 px-3 text-sm text-white/70 min-[900px]:hidden"
            :aria-expanded="showFilters"
            @click="showFilters = !showFilters"
          >
            {{ showFilters ? '收起' : '展开' }}
            <ChevronDown :size="15" :class="showFilters ? 'rotate-180' : ''" class="transition-transform" aria-hidden="true" />
          </button>
        </div>

        <div :class="showFilters ? 'grid' : 'hidden'" class="mt-3 grid-cols-1 gap-3 min-[560px]:grid-cols-2 min-[900px]:mt-0 min-[900px]:flex min-[900px]:items-end min-[900px]:justify-end">
          <label class="text-xs font-bold text-white/55">
            <span class="sr-only">状态</span>
            <select v-model="dedupStore.state.filterStatus" @change="onFiltersChanged" class="block h-10 w-full min-w-36 rounded-lg border border-white/12 bg-sidebar px-3 text-sm font-medium text-white focus:border-accent focus:outline-none">
              <option value="pending">待处理</option>
              <option value="merged">已保留左侧</option>
              <option value="replaced">已采用右侧路径</option>
              <option value="kept_both">已标记非重复</option>
              <option value="ignored">已忽略</option>
              <option value="all">全部状态</option>
            </select>
          </label>
          <label class="text-xs font-bold text-white/55">
            <span class="sr-only">置信等级</span>
            <select v-model="dedupStore.state.filterLevel" @change="onFiltersChanged" class="block h-10 w-full min-w-36 rounded-lg border border-white/12 bg-sidebar px-3 text-sm font-medium text-white focus:border-accent focus:outline-none">
              <option value="">所有等级</option>
              <option value="strong_duplicate">高置信度</option>
              <option value="suspected_duplicate">中置信度</option>
              <option value="weak_suspected">低置信度</option>
            </select>
          </label>
          <label class="text-xs font-bold text-white/55">
            <span class="sr-only">类型</span>
            <select v-model="dedupStore.state.filterMediaType" @change="onFiltersChanged" class="block h-10 w-full min-w-32 rounded-lg border border-white/12 bg-sidebar px-3 text-sm font-medium text-white focus:border-accent focus:outline-none">
              <option value="">所有类型</option>
              <option value="video">视频</option>
              <option value="manga">漫画</option>
              <option value="image">杂图</option>
              <option value="audio">音频</option>
            </select>
          </label>
          <label class="text-xs font-bold text-white/55">
            <span class="sr-only">排序</span>
            <select v-model="dedupStore.state.sort" @change="onFiltersChanged" class="block h-10 w-full min-w-36 rounded-lg border border-white/12 bg-sidebar px-3 text-sm font-medium text-white focus:border-accent focus:outline-none">
              <option value="confidence">置信度优先</option>
              <option value="newest">最新发现</option>
              <option value="oldest">最早发现</option>
            </select>
          </label>
        </div>
      </section>

      <section aria-label="重复候选列表" class="overflow-hidden rounded-2xl border border-white/10 bg-white/[0.025]">
        <div class="hidden min-[1050px]:grid min-[1050px]:grid-cols-[44px_110px_90px_minmax(0,1fr)_minmax(150px,.75fr)_minmax(0,1fr)_150px] items-center gap-3 border-b border-white/10 bg-white/[0.035] px-4 py-3 text-xs font-bold text-white/45">
          <span aria-hidden="true"></span><span>置信度</span><span>类型</span><span>左侧记录</span><span>差异</span><span>右侧记录</span><span>操作</span>
        </div>

        <div v-if="loading && pairs.length === 0" aria-live="polite" class="space-y-px">
          <div v-for="index in 5" :key="index" class="h-24 animate-pulse border-b border-white/5 bg-white/[0.035]"></div>
        </div>

        <article v-for="pair in pairs" :key="pair.id" :class="expandedPairId === pair.id ? 'bg-accent/[0.035]' : selectedPairIds.has(pair.id) ? 'bg-accent/[0.025]' : ''" class="border-b border-white/8 last:border-b-0">
          <div class="grid gap-3 px-4 py-3 min-[1050px]:grid-cols-[44px_110px_90px_minmax(0,1fr)_minmax(150px,.75fr)_minmax(0,1fr)_150px] min-[1050px]:items-center">
            <div class="flex items-center justify-between min-[1050px]:block">
              <label v-if="pair.status === 'pending'" class="flex h-10 w-10 cursor-pointer items-center justify-center rounded-lg hover:bg-white/5">
                <span class="sr-only">选择 {{ pair.existing.title }} 与 {{ pair.candidate.title }}</span>
                <input type="checkbox" :checked="selectedPairIds.has(pair.id)" @change="toggleSelected(pair.id)" class="h-4 w-4 rounded border-white/30 bg-black/30 accent-[rgb(var(--color-accent))]" />
              </label>
              <span v-else class="text-xs font-bold text-white/45">{{ statusLabel(pair.status) }}</span>
              <span class="text-xs text-white/40 min-[1050px]:hidden">#{{ pair.id }}</span>
            </div>

            <div>
              <span :class="confidenceMeta(pair.level).cls" class="inline-flex rounded-lg border px-2.5 py-1.5 text-xs font-black">{{ confidenceMeta(pair.level).label }}</span>
            </div>

            <div class="flex items-center gap-2 text-sm font-bold text-white/65">
              <component :is="typeMeta(pair.existing.media_type).icon" :size="18" aria-hidden="true" />
              {{ typeMeta(pair.existing.media_type).label }}
            </div>

            <div class="min-w-0">
              <p class="truncate text-sm font-black text-white">{{ pair.existing.title }}</p>
              <p class="mt-1 truncate text-xs text-white/45">{{ pair.existing.display_path }}</p>
              <p class="mt-1 text-xs text-white/55">{{ formatSize(pair.existing.file_size) }} · {{ mediaMetric(pair.existing) }}</p>
            </div>

            <div class="flex flex-wrap gap-1.5">
              <span v-for="delta in deltaSummary(pair)" :key="delta" class="rounded-md bg-amber-400/10 px-2 py-1 text-xs font-bold text-amber-100">{{ delta }}</span>
            </div>

            <div class="min-w-0">
              <p class="truncate text-sm font-black text-white">{{ pair.candidate.title }}</p>
              <p class="mt-1 truncate text-xs text-white/45">{{ pair.candidate.display_path }}</p>
              <p class="mt-1 text-xs text-white/55">{{ formatSize(pair.candidate.file_size) }} · {{ mediaMetric(pair.candidate) }}</p>
            </div>

            <button
              type="button"
              @click="toggleExpanded(pair.id)"
              :aria-expanded="expandedPairId === pair.id"
              class="flex h-10 items-center justify-center gap-2 rounded-lg border border-white/12 bg-white/5 px-3 text-sm font-bold text-white/75 hover:bg-white/10 hover:text-white focus-visible:ring-2 focus-visible:ring-accent"
            >
              {{ expandedPairId === pair.id ? '收起详情' : '查看差异' }}
              <ChevronDown :size="15" :class="expandedPairId === pair.id ? 'rotate-180' : ''" class="transition-transform" aria-hidden="true" />
            </button>
          </div>

          <div v-if="expandedPairId === pair.id" class="border-t border-accent/20 bg-black/15 p-4 min-[900px]:p-5">
            <div class="mb-4 flex flex-wrap items-center gap-2">
              <span class="flex items-center gap-1.5 text-sm font-black text-white"><ShieldCheck :size="17" class="text-accent" aria-hidden="true" />检测证据</span>
              <span v-for="evidence in evidenceTags(pair)" :key="evidence" class="rounded-lg border border-white/10 bg-white/5 px-2.5 py-1 text-xs font-bold text-white/65">{{ evidence }}</span>
            </div>

            <div class="grid gap-4 min-[900px]:grid-cols-[minmax(0,1fr)_minmax(270px,.8fr)_minmax(0,1fr)]">
              <section class="min-w-0" aria-label="左侧现有记录">
                <p class="mb-2 text-sm font-black text-emerald-300">左侧 · 现有记录</p>
                <div class="flex gap-3">
                  <div class="flex h-36 w-24 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-black/30">
                    <img v-if="pair.existing.cover_path" :src="thumbnailUrl(pair.existing.cover_path)" :alt="`${pair.existing.title} 封面`" class="h-full w-full object-cover" />
                    <component v-else :is="typeMeta(pair.existing.media_type).icon" :size="30" class="text-white/25" aria-hidden="true" />
                  </div>
                  <div class="min-w-0 space-y-2">
                    <p class="text-base font-black leading-snug text-white">{{ pair.existing.title }}</p>
                    <p v-if="pair.existing.favorite" class="flex items-center gap-1.5 text-xs font-bold text-amber-200"><Star :size="14" fill="currentColor" aria-hidden="true" />已收藏</p>
                    <p :class="pair.existing.is_missing ? 'text-red-200' : 'text-emerald-200'" class="text-xs font-bold">{{ pair.existing.is_missing ? '文件丢失' : '文件存在' }}</p>
                  </div>
                </div>
                <div class="mt-3 flex items-start gap-2 rounded-lg border border-white/10 bg-black/20 p-3">
                  <p class="min-w-0 flex-1 break-all font-mono text-xs leading-relaxed text-white/60">{{ pair.existing.display_path }}</p>
                  <button type="button" :aria-label="`复制左侧路径`" @click="copyPath(pair.existing)" class="shrink-0 rounded-md p-2 text-white/50 hover:bg-white/10 hover:text-white focus-visible:ring-2 focus-visible:ring-accent">
                    <Check v-if="copiedMediaId === pair.existing.id" :size="15" class="text-emerald-300" aria-hidden="true" />
                    <Copy v-else :size="15" aria-hidden="true" />
                  </button>
                </div>
              </section>

              <section aria-label="逐项差异" class="overflow-hidden rounded-xl border border-white/10">
                <div v-for="row in comparisonRows(pair)" :key="row.label" class="grid grid-cols-[82px_1fr_1fr] border-b border-white/8 last:border-b-0">
                  <span class="bg-white/[0.035] px-3 py-2.5 text-xs font-bold text-white/45">{{ row.label }}</span>
                  <span :class="row.same ? 'text-emerald-200' : 'text-white/70'" class="break-all border-l border-white/8 px-3 py-2.5 text-xs leading-relaxed">{{ row.left }}</span>
                  <span :class="row.same ? 'text-emerald-200' : 'bg-amber-400/[0.055] text-amber-100'" class="break-all border-l border-white/8 px-3 py-2.5 text-xs leading-relaxed">{{ row.right }}</span>
                </div>
              </section>

              <section class="min-w-0" aria-label="右侧新扫描记录">
                <p class="mb-2 text-sm font-black text-amber-300">右侧 · 新扫描记录</p>
                <div class="flex gap-3">
                  <div class="flex h-36 w-24 shrink-0 items-center justify-center overflow-hidden rounded-xl border border-white/10 bg-black/30">
                    <img v-if="pair.candidate.cover_path" :src="thumbnailUrl(pair.candidate.cover_path)" :alt="`${pair.candidate.title} 封面`" class="h-full w-full object-cover" />
                    <component v-else :is="typeMeta(pair.candidate.media_type).icon" :size="30" class="text-white/25" aria-hidden="true" />
                  </div>
                  <div class="min-w-0 space-y-2">
                    <p class="text-base font-black leading-snug text-white">{{ pair.candidate.title }}</p>
                    <p v-if="pair.candidate.favorite" class="flex items-center gap-1.5 text-xs font-bold text-amber-200"><Star :size="14" fill="currentColor" aria-hidden="true" />已收藏</p>
                    <p :class="pair.candidate.is_missing ? 'text-red-200' : 'text-emerald-200'" class="text-xs font-bold">{{ pair.candidate.is_missing ? '文件丢失' : '文件存在' }}</p>
                  </div>
                </div>
                <div class="mt-3 flex items-start gap-2 rounded-lg border border-white/10 bg-black/20 p-3">
                  <p class="min-w-0 flex-1 break-all font-mono text-xs leading-relaxed text-white/60">{{ pair.candidate.display_path }}</p>
                  <button type="button" :aria-label="`复制右侧路径`" @click="copyPath(pair.candidate)" class="shrink-0 rounded-md p-2 text-white/50 hover:bg-white/10 hover:text-white focus-visible:ring-2 focus-visible:ring-accent">
                    <Check v-if="copiedMediaId === pair.candidate.id" :size="15" class="text-emerald-300" aria-hidden="true" />
                    <Copy v-else :size="15" aria-hidden="true" />
                  </button>
                </div>
              </section>
            </div>

            <div v-if="pair.status === 'pending'" class="mt-5 grid gap-2 border-t border-white/10 pt-4 min-[700px]:grid-cols-2 min-[1180px]:grid-cols-[1.1fr_1.1fr_1fr_auto]">
              <button type="button" :disabled="processingPairIds.has(pair.id)" @click="onResolve(pair, 'keep_existing')" class="min-h-12 rounded-xl bg-accent px-4 py-2 text-left text-sm font-black text-white hover:brightness-110 focus-visible:ring-2 focus-visible:ring-white/70 disabled:opacity-50">
                保留左侧记录
                <span class="mt-0.5 block text-xs font-medium text-white/70">右侧文件保留，但从媒体库隐藏</span>
              </button>
              <button type="button" :disabled="!pair.existing.is_missing || processingPairIds.has(pair.id)" @click="onResolve(pair, 'replace_path')" class="min-h-12 rounded-xl border border-white/14 bg-white/5 px-4 py-2 text-left text-sm font-black text-white hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent disabled:cursor-not-allowed disabled:opacity-40">
                采用右侧路径
                <span class="mt-0.5 block text-xs font-medium text-white/55">仅当左侧文件丢失时可用</span>
              </button>
              <button type="button" :disabled="processingPairIds.has(pair.id)" @click="onResolve(pair, 'keep_both')" class="min-h-12 rounded-xl border border-white/12 bg-white/5 px-4 py-2 text-left text-sm font-black text-white/85 hover:bg-white/10 hover:text-white focus-visible:ring-2 focus-visible:ring-accent disabled:opacity-50">
                两者不是重复
                <span class="mt-0.5 block text-xs font-medium text-white/50">保留两条媒体记录</span>
              </button>
              <button type="button" :disabled="processingPairIds.has(pair.id)" @click="askDeleteFile(pair, $event)" class="flex min-h-12 items-center justify-center gap-2 rounded-xl border border-red-400/25 bg-red-400/10 px-4 text-sm font-black text-red-100 hover:bg-red-400/20 focus-visible:ring-2 focus-visible:ring-red-300 disabled:opacity-50">
                <Trash2 :size="17" aria-hidden="true" /> 文件清理
              </button>
            </div>
            <div v-else class="mt-4 rounded-xl border border-white/10 bg-white/[0.035] px-4 py-3 text-sm text-white/60">
              <span class="font-black text-white">{{ statusLabel(pair.status) }}</span>
              <span v-if="pair.resolution_note"> · {{ pair.resolution_note }}</span>
            </div>
          </div>
        </article>

        <div v-if="noPairs" class="flex flex-col items-center justify-center px-6 py-20 text-center">
          <ShieldCheck :size="42" class="mb-4 text-emerald-300/70" aria-hidden="true" />
          <p class="text-lg font-black text-white">当前没有符合条件的重复条目</p>
          <p class="mt-2 max-w-md text-sm leading-relaxed text-white/50">新扫描文件经过指纹检测后会显示在这里。你也可以调整筛选条件查看处理历史。</p>
        </div>
      </section>

      <footer class="flex flex-wrap items-center justify-between gap-3 px-1 text-sm text-white/50">
        <div class="flex flex-wrap items-center gap-2">
          <span>显示 {{ rangeStart }}–{{ rangeEnd }}，共 {{ total }} 组</span>
          <template v-if="selectedCount">
            <span class="text-white/25">·</span>
            <span class="font-bold text-white/75">已选择 {{ selectedCount }} 组</span>
            <button type="button" @click="clearSelection" class="h-9 rounded-lg px-2.5 text-xs font-bold text-white/60 hover:bg-white/10 hover:text-white">取消选择</button>
            <button type="button" @click="onBatchNotDuplicate" class="flex h-9 items-center gap-1.5 rounded-lg bg-accent px-3 text-xs font-black text-white hover:brightness-110 focus-visible:ring-2 focus-visible:ring-white/70">
              <Check :size="15" aria-hidden="true" /> 批量标记为不是重复
            </button>
          </template>
        </div>
        <div class="flex items-center gap-2">
          <button type="button" aria-label="上一页" :disabled="dedupStore.state.page <= 1 || loading" @click="goToPage(dedupStore.state.page - 1)" class="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 disabled:opacity-35">
            <ChevronLeft :size="17" aria-hidden="true" />
          </button>
          <span class="min-w-20 text-center font-bold text-white/70">{{ dedupStore.state.page }} / {{ totalPages }}</span>
          <button type="button" aria-label="下一页" :disabled="dedupStore.state.page >= totalPages || loading" @click="goToPage(dedupStore.state.page + 1)" class="flex h-10 w-10 items-center justify-center rounded-lg border border-white/10 bg-white/5 hover:bg-white/10 disabled:opacity-35">
            <ChevronRight :size="17" aria-hidden="true" />
          </button>
        </div>
      </footer>
    </main>

    <Teleport to="body">
      <Transition name="fade">
        <div v-if="confirmDeletePair" class="fixed inset-0 z-50 flex items-center justify-center bg-background/80 p-4" @click.self="closeDeleteModal" @keydown="onModalKeydown">
          <div ref="modalPanel" role="dialog" aria-modal="true" aria-labelledby="dedup-delete-title" aria-describedby="dedup-delete-description" class="w-full max-w-lg rounded-2xl border border-white/12 bg-[rgb(var(--color-sidebar))] p-6 shadow-2xl">
            <div class="flex items-start gap-3">
              <div class="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-red-500/15 text-red-300"><AlertTriangle :size="21" aria-hidden="true" /></div>
              <div>
                <h2 id="dedup-delete-title" class="text-lg font-black text-white">永久删除右侧文件</h2>
                <p id="dedup-delete-description" class="mt-1 text-sm leading-relaxed text-white/60">操作不可撤销。系统会先验证文件位于已配置的媒体库目录内，再从磁盘和媒体库中删除。</p>
              </div>
            </div>
            <div class="mt-5 rounded-xl border border-white/10 bg-black/25 p-4">
              <p class="font-black text-white">{{ confirmDeletePair.candidate.title }}</p>
              <p class="mt-2 break-all font-mono text-xs leading-relaxed text-white/50">{{ confirmDeletePair.candidate.display_path }}</p>
              <p class="mt-2 text-sm text-white/65">{{ formatSize(confirmDeletePair.candidate.file_size) }} · {{ typeMeta(confirmDeletePair.candidate.media_type).label }}</p>
            </div>
            <div class="mt-5 grid grid-cols-2 gap-3">
              <button ref="cancelDeleteButton" type="button" @click="closeDeleteModal" class="h-11 rounded-xl border border-white/12 bg-white/5 text-sm font-bold text-white/75 hover:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent">取消</button>
              <button type="button" @click="onDeleteConfirmed" class="flex h-11 items-center justify-center gap-2 rounded-xl bg-red-500 text-sm font-black text-white hover:brightness-110 focus-visible:ring-2 focus-visible:ring-red-200"><Trash2 :size="16" aria-hidden="true" />确认永久删除</button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
