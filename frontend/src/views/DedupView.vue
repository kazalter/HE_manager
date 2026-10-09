<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import {
  AlertTriangle,
  Check,
  ChevronDown,
  Copy,
  Eye,
  FileImage,
  Film,
  Headphones,
  Layers,
  RefreshCw,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  Trash2,
  X,
} from 'lucide-vue-next'
import { thumbnailUrl } from '../config'
import { dedupStore } from '../stores/dedupStore'
import type { DedupMediaSummary, DuplicateCandidatePair } from '../types'
import PaginationControl from '../components/PaginationControl.vue'
import { EmptyState, PageHeader, UiBadge, UiButton, UiCard, UiIconButton, UiModal, UiSkeleton, controlClass, type Tone } from '../components/ui'

const previewModalPair = ref<DuplicateCandidatePair | null>(null)

const getQualityComparison = (pair: DuplicateCandidatePair) => {
  const leftRes = (pair.existing.width || 0) * (pair.existing.height || 0)
  const rightRes = (pair.candidate.width || 0) * (pair.candidate.height || 0)

  if (leftRes > rightRes && rightRes > 0) return 'left'
  if (rightRes > leftRes && leftRes > 0) return 'right'

  return 'equal'
}

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
const deleteModalOpen = computed({
  get: () => !!confirmDeletePair.value,
  set: (value: boolean) => { if (!value) closeDeleteModal() },
})
const previewModalOpen = computed({
  get: () => !!previewModalPair.value,
  set: (value: boolean) => { if (!value) previewModalPair.value = null },
})
const selectClass = `${controlClass('md')} select-native`

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

const confidenceMeta = (level: string): { label: string; short: string; tone: Tone } => {
  if (level === 'strong_duplicate') return { label: '高置信度', short: '高', tone: 'danger' }
  if (level === 'suspected_duplicate') return { label: '中置信度', short: '中', tone: 'warning' }
  return { label: '低置信度', short: '低', tone: 'info' }
}

const statusLabel = (status: string) => ({
  pending: '待处理',
  merged: '已保留左侧',
  replaced: '已采用右侧路径',
  kept_both: '已标记非重复',
  ignored: '已忽略',
  stale: '检测结果已失效',
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
const scanActive = computed(() => dedupStore.state.scanStarting || (summary.value?.checking ?? 0) > 0 || (summary.value?.queue_size ?? 0) > 0)
const coverage = computed(() => summary.value?.total_media
  ? Math.round((summary.value.fingerprinted / summary.value.total_media) * 100) : 0)
const hasFilters = computed(() => !!dedupStore.state.filterLevel || !!dedupStore.state.filterMediaType || dedupStore.state.filterStatus !== 'pending')
let pollTimer: ReturnType<typeof window.setTimeout> | undefined
let disposed = false

const schedulePoll = () => {
  if (disposed || pollTimer !== undefined || !scanActive.value) return
  pollTimer = window.setTimeout(async () => {
    pollTimer = undefined
    await dedupStore.refresh()
    schedulePoll()
  }, 3000)
}

watch(scanActive, (active) => {
  if (active) schedulePoll()
  else if (pollTimer !== undefined) {
    window.clearTimeout(pollTimer)
    pollTimer = undefined
  }
})

const onRecheckLibrary = async () => {
  if (scanActive.value) return
  await dedupStore.recheckLibrary()
}

const resetFilters = async () => {
  dedupStore.setFilters({ level: '', status: 'pending', mediaType: '' })
  await dedupStore.fetchPairs()
}

watch(pairs, (nextPairs) => {
  const validIds = new Set(nextPairs.map(pair => pair.id))
  selectedPairIds.value = new Set([...selectedPairIds.value].filter(id => validIds.has(id)))
  if (!expandedPairId.value || !validIds.has(expandedPairId.value)) {
    expandedPairId.value = nextPairs[0]?.id ?? null
  }
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

const handleGlobalEscape = (event: KeyboardEvent) => {
  if (event.key === 'Escape') {
    if (confirmDeletePair.value) closeDeleteModal()
    if (previewModalPair.value) previewModalPair.value = null
  }
}

onMounted(async () => {
  window.addEventListener('keydown', handleGlobalEscape)
  await dedupStore.refresh()
})

onBeforeUnmount(() => {
  disposed = true
  if (pollTimer !== undefined) window.clearTimeout(pollTimer)
  window.removeEventListener('keydown', handleGlobalEscape)
})
</script>

<template>
  <div class="relative min-h-full">
    <PageHeader title="重复管理" :count="`${summary?.pending_pairs ?? 0} 待处理`" description="按文件内容寻找重复，支持改名后的副本。检测只生成待审查结果，保留与清理由你决定。">
      <template #actions>
        <UiButton variant="secondary" class="pointer-coarse:h-11" :disabled="loading" aria-label="刷新检测状态" @click="onRefresh">
          <template #icon><RefreshCw :size="16" :class="(loading || refreshSpinning) ? 'animate-spin' : ''" aria-hidden="true" /></template>
          <span class="hidden min-[480px]:inline">刷新状态</span>
        </UiButton>
        <UiButton variant="primary" class="pointer-coarse:h-11" :disabled="scanActive || !summary?.total_media" @click="onRecheckLibrary">
          <template #icon><RefreshCw :size="16" :class="scanActive ? 'animate-spin' : ''" aria-hidden="true" /></template>
          {{ scanActive ? '检测进行中' : '检测全库' }}
        </UiButton>
      </template>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container space-y-4">
        <div
          v-if="errorMessage"
          role="alert"
          class="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger"
        >
          <AlertTriangle :size="18" class="mt-0.5 shrink-0" aria-hidden="true" />
          <span class="min-w-0 flex-1">{{ errorMessage }}</span>
          <UiIconButton label="关闭错误提示" size="sm" class="-my-1 -mr-1.5" @click="dedupStore.clearError()"><X :size="16" aria-hidden="true" /></UiIconButton>
        </div>

        <!-- 内容检测 -->
        <UiCard as="section" padding="none" aria-label="内容检测">
          <div class="grid grid-cols-2 divide-line min-[900px]:grid-cols-4 min-[900px]:divide-x" aria-live="polite">
            <div class="border-b border-line p-4 sm:px-5 min-[900px]:border-b-0">
              <p class="text-meta text-subtle">可检测媒体</p>
              <p class="mt-1 text-title font-semibold text-ink tabular-nums">{{ summary?.total_media?.toLocaleString() ?? '—' }}<span class="ml-1 text-meta font-normal text-subtle">项</span></p>
            </div>
            <div class="border-b border-l border-line p-4 sm:px-5 min-[900px]:border-b-0 min-[900px]:border-l-0">
              <p class="text-meta text-subtle">已建立指纹</p>
              <p class="mt-1 text-title font-semibold text-ink tabular-nums">{{ summary?.fingerprinted?.toLocaleString() ?? '—' }}<span class="ml-1 text-meta font-normal text-subtle">项</span></p>
            </div>
            <div class="p-4 sm:px-5">
              <p class="text-meta text-subtle">待审查结果</p>
              <p class="mt-1 text-title font-semibold text-ink tabular-nums">{{ summary?.pending_pairs ?? '—' }}<span class="ml-1 text-meta font-normal text-subtle">组</span></p>
              <p class="mt-1 flex flex-wrap gap-x-2 text-caption text-subtle tabular-nums">
                <span><span class="text-danger">{{ summary?.strong_duplicate ?? 0 }}</span> 高</span>
                <span><span class="text-warning">{{ summary?.suspected_duplicate ?? 0 }}</span> 中</span>
                <span><span class="text-info">{{ summary?.weak_suspected ?? 0 }}</span> 低</span>
              </p>
            </div>
            <div class="border-l border-line p-4 sm:px-5 min-[900px]:border-l-0">
              <p class="text-meta text-subtle">检测失败</p>
              <p class="mt-1 text-title font-semibold tabular-nums" :class="summary?.failed ? 'text-warning' : 'text-ink'">{{ summary?.failed ?? '—' }}<span class="ml-1 text-meta font-normal text-subtle">项</span></p>
            </div>
          </div>
          <div class="border-t border-line px-4 py-3.5 sm:px-5">
            <div class="flex flex-wrap items-center justify-between gap-x-4 gap-y-1 text-meta">
              <span class="text-muted tabular-nums">指纹覆盖 {{ coverage }}%</span>
              <span v-if="scanActive" role="status" class="flex items-center gap-2 text-info">
                <span class="size-1.5 animate-pulse rounded-full bg-info" aria-hidden="true"></span>
                后台检测中 · {{ summary?.checking ?? 0 }} 项等待处理 · 队列 {{ summary?.queue_size ?? 0 }}
              </span>
              <span v-else-if="summary?.unchecked" class="text-subtle">{{ summary.unchecked }} 项尚未建立指纹，建议检测全库</span>
              <span v-else class="text-subtle">检测任务空闲 · 支持视频、漫画、图片和音频</span>
            </div>
            <div class="mt-2 h-1 overflow-hidden rounded-sm bg-surface-3" role="progressbar" aria-label="指纹覆盖率" :aria-valuenow="coverage" aria-valuemin="0" aria-valuemax="100"><div class="h-full rounded-sm bg-accent" :style="{ width: `${coverage}%` }"></div></div>
            <p v-if="summary?.failed" class="mt-3 flex items-start gap-2 text-meta text-warning"><AlertTriangle :size="16" class="mt-0.5 shrink-0" aria-hidden="true" />{{ summary.failed }} 项检测失败，请检查文件可读性后重新检测。</p>
            <p class="mt-2 text-caption text-subtle">图片比较文件指纹；漫画、视频和音频比较抽样内容。同名文件还会比较页数、时长等信息。压缩或转码后的不同版本可能无法识别。</p>
          </div>
        </UiCard>

        <!-- 筛选与排序 -->
        <section aria-label="筛选与排序" class="pt-2">
          <div class="flex items-center justify-between gap-3 min-[900px]:hidden">
            <span class="text-meta text-subtle tabular-nums">共 {{ total }} 组</span>
            <UiButton variant="secondary" size="sm" class="pointer-coarse:h-10" :aria-expanded="showFilters" @click="showFilters = !showFilters">
              <template #icon><SlidersHorizontal :size="14" aria-hidden="true" /></template>
              筛选与排序
              <template #trailing><ChevronDown :size="14" :class="showFilters ? 'rotate-180' : ''" class="transition-transform" aria-hidden="true" /></template>
            </UiButton>
          </div>
          <div :class="showFilters ? 'grid' : 'hidden'" class="mt-3 grid-cols-2 gap-2 min-[900px]:mt-0 min-[900px]:flex min-[900px]:items-center min-[900px]:gap-3">
            <span class="hidden text-meta text-subtle tabular-nums min-[900px]:mr-auto min-[900px]:inline">共 {{ total }} 组 · 当前支持视频、漫画、杂图和音频</span>
            <label class="block min-[900px]:w-44">
              <span class="sr-only">状态</span>
              <select v-model="dedupStore.state.filterStatus" @change="onFiltersChanged" :class="selectClass">
                <option value="pending">待处理</option>
                <option value="merged">已保留左侧</option>
                <option value="replaced">已采用右侧路径</option>
                <option value="kept_both">已标记非重复</option>
                <option value="ignored">已忽略</option>
                <option value="stale">检测结果已失效</option>
                <option value="all">全部状态</option>
              </select>
            </label>
            <label class="block min-[900px]:w-36">
              <span class="sr-only">置信等级</span>
              <select v-model="dedupStore.state.filterLevel" @change="onFiltersChanged" :class="selectClass">
                <option value="">所有等级</option>
                <option value="strong_duplicate">高置信度</option>
                <option value="suspected_duplicate">中置信度</option>
                <option value="weak_suspected">低置信度</option>
              </select>
            </label>
            <label class="block min-[900px]:w-32">
              <span class="sr-only">类型</span>
              <select v-model="dedupStore.state.filterMediaType" @change="onFiltersChanged" :class="selectClass">
                <option value="">所有类型</option>
                <option value="video">视频</option>
                <option value="manga">漫画</option>
                <option value="image">杂图</option>
                <option value="audio">音频</option>
              </select>
            </label>
            <label class="block min-[900px]:w-36">
              <span class="sr-only">排序</span>
              <select v-model="dedupStore.state.sort" @change="onFiltersChanged" :class="selectClass">
                <option value="confidence">置信度优先</option>
                <option value="newest">最新发现</option>
                <option value="oldest">最早发现</option>
              </select>
            </label>
          </div>
        </section>

        <!-- 重复候选列表 -->
        <UiCard as="section" padding="none" aria-label="重复候选列表" class="overflow-hidden">
          <div class="hidden h-10 items-center gap-3 border-b border-line px-4 text-caption font-medium text-subtle min-[1050px]:grid min-[1050px]:grid-cols-[40px_88px_72px_minmax(0,1fr)_minmax(140px,.7fr)_minmax(0,1fr)_120px]">
            <span aria-hidden="true"></span><span>置信度</span><span>类型</span><span>左侧记录</span><span>差异</span><span>右侧记录</span><span class="text-right">操作</span>
          </div>

          <div v-if="loading && pairs.length === 0" aria-live="polite" class="divide-y divide-line">
            <div v-for="index in 5" :key="index" class="flex items-center gap-4 px-4 py-4">
              <UiSkeleton class="h-5 w-16 rounded-md" />
              <div class="flex-1 space-y-2"><UiSkeleton shape="text" class="w-2/3" /><UiSkeleton shape="text" class="w-1/3" /></div>
            </div>
          </div>

          <article
            v-for="pair in pairs"
            :key="pair.id"
            :class="expandedPairId === pair.id ? 'bg-surface-2/40' : selectedPairIds.has(pair.id) ? 'bg-accent/8 shadow-[inset_2px_0_0_rgb(var(--color-accent))]' : ''"
            class="border-b border-line last:border-b-0"
          >
            <div class="grid gap-3 px-4 py-3 min-[1050px]:grid-cols-[40px_88px_72px_minmax(0,1fr)_minmax(140px,.7fr)_minmax(0,1fr)_120px] min-[1050px]:items-center">
              <!-- mobile: one meta line; desktop: three grid cells -->
              <div class="flex items-center gap-2 min-[1050px]:contents">
                <div class="-ml-2 min-[1050px]:ml-0">
                  <label v-if="pair.status === 'pending'" class="flex size-10 cursor-pointer items-center justify-center rounded-lg hover:bg-surface-2">
                    <span class="sr-only">选择 {{ pair.existing.title }} 与 {{ pair.candidate.title }}</span>
                    <input type="checkbox" :checked="selectedPairIds.has(pair.id)" @change="toggleSelected(pair.id)" class="size-4 rounded-sm accent-accent" />
                  </label>
                  <UiBadge v-else class="ml-2 min-[1050px]:ml-0">{{ statusLabel(pair.status) }}</UiBadge>
                </div>
                <div><UiBadge :tone="confidenceMeta(pair.level).tone">{{ confidenceMeta(pair.level).label }}</UiBadge></div>
                <div class="flex items-center gap-1.5 text-meta text-muted">
                  <component :is="typeMeta(pair.existing.media_type).icon" :size="16" class="text-subtle" aria-hidden="true" />
                  {{ typeMeta(pair.existing.media_type).label }}
                </div>
                <span class="ml-auto text-caption text-subtle tabular-nums min-[1050px]:hidden">#{{ pair.id }}</span>
              </div>

              <div class="min-w-0">
                <p class="flex min-w-0 items-baseline gap-2"><span class="shrink-0 text-caption text-subtle min-[1050px]:hidden">左</span><span class="truncate text-body font-medium text-ink" :title="pair.existing.title">{{ pair.existing.title }}</span></p>
                <p class="mt-0.5 truncate text-caption text-subtle" :title="pair.existing.display_path">{{ pair.existing.display_path }}</p>
                <p class="mt-0.5 text-caption text-muted tabular-nums">{{ formatSize(pair.existing.file_size) }} · {{ mediaMetric(pair.existing) }}</p>
              </div>

              <div class="flex flex-wrap gap-1.5 min-[1050px]:order-none">
                <UiBadge v-for="delta in deltaSummary(pair)" :key="delta" :tone="delta === '关键属性一致' ? 'success' : 'warning'">{{ delta }}</UiBadge>
              </div>

              <div class="min-w-0">
                <p class="flex min-w-0 items-baseline gap-2"><span class="shrink-0 text-caption text-subtle min-[1050px]:hidden">右</span><span class="truncate text-body font-medium text-ink" :title="pair.candidate.title">{{ pair.candidate.title }}</span></p>
                <p class="mt-0.5 truncate text-caption text-subtle" :title="pair.candidate.display_path">{{ pair.candidate.display_path }}</p>
                <p class="mt-0.5 text-caption text-muted tabular-nums">{{ formatSize(pair.candidate.file_size) }} · {{ mediaMetric(pair.candidate) }}</p>
              </div>

              <div class="min-[1050px]:flex min-[1050px]:justify-end">
                <UiButton
                  :variant="expandedPairId === pair.id ? 'ghost' : 'secondary'"
                  size="sm"
                  class="pointer-coarse:h-10"
                  :aria-expanded="expandedPairId === pair.id"
                  @click="toggleExpanded(pair.id)"
                >
                  {{ expandedPairId === pair.id ? '收起详情' : '查看差异' }}
                  <template #trailing><ChevronDown :size="14" :class="expandedPairId === pair.id ? 'rotate-180' : ''" class="transition-transform" aria-hidden="true" /></template>
                </UiButton>
              </div>
            </div>

            <div v-if="expandedPairId === pair.id" class="border-t border-line bg-background/40 p-4 min-[900px]:p-5">
              <div class="mb-4 flex flex-wrap items-center gap-2">
                <span class="flex items-center gap-1.5 text-meta font-medium text-ink"><ShieldCheck :size="16" class="text-subtle" aria-hidden="true" />检测证据</span>
                <UiBadge v-for="evidence in evidenceTags(pair)" :key="evidence">{{ evidence }}</UiBadge>
              </div>

              <div class="grid gap-4 min-[900px]:grid-cols-2">
                <section
                  v-for="side in [
                    { key: 'left', media: pair.existing, title: '左侧 · 现有记录', aria: '左侧现有记录', copy: '复制左侧路径' },
                    { key: 'right', media: pair.candidate, title: '右侧 · 新扫描记录', aria: '右侧新扫描记录', copy: '复制右侧路径' },
                  ]"
                  :key="side.key"
                  class="min-w-0 rounded-lg border border-line bg-surface p-3"
                  :aria-label="side.aria"
                >
                  <div class="mb-3 flex items-center justify-between gap-2">
                    <p class="text-meta font-medium text-muted">{{ side.title }}</p>
                    <UiBadge v-if="getQualityComparison(pair) === side.key" tone="success"><Sparkles :size="12" aria-hidden="true" /> 较高分辨率</UiBadge>
                  </div>
                  <div class="flex gap-3">
                    <button type="button"
                      @click="previewModalPair = pair"
                      :aria-label="`对比 ${pair.existing.title} 与 ${pair.candidate.title} 的封面`"
                      class="group/cover relative flex h-32 w-[88px] shrink-0 cursor-pointer items-center justify-center overflow-hidden rounded-lg bg-surface-2 focus-ring"
                      title="点击并排高清对比预览"
                    >
                      <img v-if="side.media.cover_path" :src="thumbnailUrl(side.media.cover_path)" :alt="`${side.media.title} 封面`" class="h-full w-full object-cover transition-transform duration-200 group-hover/cover:scale-[1.03]" />
                      <component v-else :is="typeMeta(side.media.media_type).icon" :size="28" class="text-faint" aria-hidden="true" />
                      <span class="pointer-events-none absolute inset-0 rounded-lg ring-1 ring-inset ring-white/8"></span>
                      <span class="absolute inset-0 flex items-center justify-center bg-black/45 text-white opacity-0 transition-opacity group-hover/cover:opacity-100" aria-hidden="true">
                        <Eye :size="18" />
                      </span>
                    </button>
                    <div class="min-w-0 space-y-1.5">
                      <p class="text-body font-medium leading-snug break-words text-ink">{{ side.media.title }}</p>
                      <p v-if="side.media.favorite" class="flex items-center gap-1.5 text-meta text-star"><Star :size="14" fill="currentColor" aria-hidden="true" />已收藏</p>
                      <p :class="side.media.is_missing ? 'text-danger' : 'text-success'" class="text-meta">{{ side.media.is_missing ? '文件丢失' : '文件存在' }}</p>
                    </div>
                  </div>
                  <div class="mt-3 flex items-start gap-2 rounded-lg bg-surface-2 py-1.5 pr-1.5 pl-3">
                    <p class="min-w-0 flex-1 py-1 font-mono text-caption leading-relaxed break-all text-muted">{{ side.media.display_path }}</p>
                    <UiIconButton :label="side.copy" size="sm" @click="copyPath(side.media)">
                      <Check v-if="copiedMediaId === side.media.id" :size="15" class="text-success" aria-hidden="true" />
                      <Copy v-else :size="15" aria-hidden="true" />
                    </UiIconButton>
                  </div>
                </section>
              </div>

              <section aria-label="逐项差异" class="mt-4 overflow-hidden rounded-lg border border-line bg-surface">
                <div class="grid grid-cols-[84px_minmax(0,1fr)_minmax(0,1fr)] border-b border-line text-caption font-medium text-subtle sm:grid-cols-[96px_minmax(0,1fr)_minmax(0,1fr)]">
                  <span class="px-3 py-2">项目</span><span class="border-l border-line px-3 py-2">左侧</span><span class="border-l border-line px-3 py-2">右侧</span>
                </div>
                <div v-for="row in comparisonRows(pair)" :key="row.label" class="grid grid-cols-[84px_minmax(0,1fr)_minmax(0,1fr)] border-b border-line last:border-b-0 sm:grid-cols-[96px_minmax(0,1fr)_minmax(0,1fr)]">
                  <span class="px-3 py-2.5 text-caption text-subtle">{{ row.label }}</span>
                  <span :class="row.same ? 'text-subtle' : 'text-ink'" class="border-l border-line px-3 py-2.5 text-meta leading-relaxed break-words [overflow-wrap:anywhere]">{{ row.left }}</span>
                  <span :class="row.same ? 'text-subtle' : 'bg-warning/8 text-ink'" class="border-l border-line px-3 py-2.5 text-meta leading-relaxed break-words [overflow-wrap:anywhere]">
                    {{ row.right }}
                    <Check v-if="row.same" :size="13" class="ml-1 inline text-success" aria-label="相同" />
                  </span>
                </div>
              </section>

              <div v-if="pair.status === 'pending'" class="mt-4 grid gap-2 border-t border-line pt-4 min-[700px]:grid-cols-2 min-[1180px]:grid-cols-[1.1fr_1.1fr_1fr_auto]">
                <button type="button" :disabled="processingPairIds.has(pair.id)" @click="onResolve(pair, 'keep_existing')" class="min-h-12 rounded-lg bg-accent px-4 py-2 text-left text-body font-medium text-on-accent transition-colors hover:bg-accent/90 focus-ring disabled:opacity-45">
                  保留左侧记录
                  <span class="mt-0.5 block text-caption font-normal opacity-80">右侧文件保留，但从媒体库隐藏</span>
                </button>
                <button type="button" :disabled="!pair.existing.is_missing || processingPairIds.has(pair.id)" @click="onResolve(pair, 'replace_path')" class="min-h-12 rounded-lg border border-line bg-surface-2 px-4 py-2 text-left text-body font-medium text-ink transition-colors hover:border-line-strong hover:bg-surface-3 focus-ring disabled:cursor-not-allowed disabled:opacity-45">
                  采用右侧路径
                  <span class="mt-0.5 block text-caption font-normal text-subtle">仅当左侧文件丢失时可用</span>
                </button>
                <button type="button" :disabled="processingPairIds.has(pair.id)" @click="onResolve(pair, 'keep_both')" class="min-h-12 rounded-lg border border-line bg-surface-2 px-4 py-2 text-left text-body font-medium text-ink transition-colors hover:border-line-strong hover:bg-surface-3 focus-ring disabled:opacity-45">
                  两者不是重复
                  <span class="mt-0.5 block text-caption font-normal text-subtle">保留两条媒体记录</span>
                </button>
                <button type="button" :disabled="processingPairIds.has(pair.id)" @click="askDeleteFile(pair, $event)" class="flex min-h-12 items-center justify-center gap-2 rounded-lg border border-danger/25 bg-danger/12 px-4 text-body font-medium whitespace-nowrap text-danger transition-colors hover:bg-danger/20 focus-ring disabled:opacity-45">
                  <Trash2 :size="16" aria-hidden="true" /> 文件清理
                </button>
              </div>
              <div v-else class="mt-4 rounded-lg border border-line bg-surface-2 px-3.5 py-3 text-meta text-muted">
                <span class="font-medium text-ink">{{ statusLabel(pair.status) }}</span>
                <span v-if="pair.resolution_note"> · {{ pair.resolution_note }}</span>
              </div>
            </div>
          </article>

          <EmptyState
            v-if="noPairs"
            :icon="ShieldCheck"
            :title="scanActive ? '正在检查文件内容' : hasFilters ? '当前筛选下没有结果' : summary?.unchecked ? '还有文件尚未检测' : '当前没有待审查的重复条目'"
            :description="scanActive ? '后台检测持续进行，发现的重复条目会自动显示在这里。' : hasFilters ? '调整筛选条件，或返回全部待审查结果。' : summary?.unchecked ? '列表为空不代表没有重复。点击上方“检测全库”补全指纹并重新检查。' : '可以重新检测全库，或通过状态筛选查看处理历史。'"
          >
            <UiButton v-if="hasFilters" variant="secondary" size="sm" @click="resetFilters">清除筛选</UiButton>
          </EmptyState>
        </UiCard>

        <footer class="flex flex-wrap items-center justify-between gap-3 text-meta text-subtle">
          <div class="flex min-h-9 flex-wrap items-center gap-2">
            <span class="tabular-nums">显示 {{ rangeStart }}–{{ rangeEnd }}，共 {{ total }} 组</span>
            <template v-if="selectedCount">
              <span class="text-faint" aria-hidden="true">·</span>
              <span class="font-medium text-ink tabular-nums">已选择 {{ selectedCount }} 组</span>
              <UiButton variant="ghost" size="sm" @click="clearSelection">取消选择</UiButton>
              <UiButton variant="primary" size="sm" @click="onBatchNotDuplicate">
                <template #icon><Check :size="14" aria-hidden="true" /></template>
                批量标记为不是重复
              </UiButton>
            </template>
          </div>
          <PaginationControl
            v-if="totalPages > 1"
            :page="dedupStore.state.page"
            :page-count="totalPages"
            :total-items="total"
            :page-size="dedupStore.state.pageSize"
            :disabled="loading"
            item-label="组重复"
            @change="goToPage"
          />
        </footer>
      </div>
    </div>

    <UiModal
      v-model:open="deleteModalOpen"
      title="永久删除右侧文件"
      description="操作不可撤销。系统会先验证文件位于已配置的媒体库目录内，再从磁盘和媒体库中删除。"
      size="sm"
    >
      <div v-if="confirmDeletePair" class="rounded-lg border border-line bg-surface-2 p-3.5">
        <p class="text-body font-medium break-words text-ink">{{ confirmDeletePair.candidate.title }}</p>
        <p class="mt-1.5 font-mono text-caption leading-relaxed break-all text-subtle">{{ confirmDeletePair.candidate.display_path }}</p>
        <p class="mt-1.5 text-meta text-muted tabular-nums">{{ formatSize(confirmDeletePair.candidate.file_size) }} · {{ typeMeta(confirmDeletePair.candidate.media_type).label }}</p>
      </div>
      <template #footer>
        <UiButton variant="ghost" autofocus @click="closeDeleteModal">取消</UiButton>
        <UiButton variant="danger" @click="onDeleteConfirmed">
          <template #icon><Trash2 :size="16" aria-hidden="true" /></template>
          确认永久删除
        </UiButton>
      </template>
    </UiModal>

    <UiModal
      v-model:open="previewModalOpen"
      title="封面与画质并排对比"
      description="左侧现有 vs 右侧新扫描 · 点击背景或按 Esc 退出"
      size="xl"
    >
      <div v-if="previewModalPair" class="grid grid-cols-1 gap-4 md:grid-cols-2">
        <div
          v-for="side in [
            { key: 'left', media: previewModalPair.existing, label: '现有记录' },
            { key: 'right', media: previewModalPair.candidate, label: '新扫描候选' },
          ]"
          :key="side.key"
          class="flex min-w-0 flex-col gap-3 rounded-2xl border border-line bg-surface p-3"
        >
          <div class="flex items-center justify-between gap-3 text-meta">
            <span class="font-medium text-ink">{{ side.label }}</span>
            <span class="text-subtle tabular-nums">
              {{ side.media.width && side.media.height ? `${side.media.width}×${side.media.height}` : '分辨率未知' }} · {{ formatSize(side.media.file_size) }}
            </span>
          </div>
          <div class="flex max-h-[52vh] min-h-[240px] w-full flex-1 items-center justify-center overflow-hidden rounded-lg bg-black/50 p-2">
            <img v-if="side.media.cover_path" :src="thumbnailUrl(side.media.cover_path)" :alt="side.media.title" class="max-h-full max-w-full rounded-sm object-contain" />
            <div v-else class="text-meta text-subtle">暂无封面</div>
          </div>
          <p class="truncate text-center text-meta text-muted" :title="side.media.title">{{ side.media.title }}</p>
        </div>
      </div>
    </UiModal>
  </div>
</template>
