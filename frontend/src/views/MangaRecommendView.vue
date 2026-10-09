<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import axios from 'axios'
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  Compass,
  Layers,
  RefreshCw,
  Save,
  Search,
  SlidersHorizontal,
  Sparkles,
  Star,
  X
} from 'lucide-vue-next'
import { API_BASE_URL, thumbnailUrl } from '../config'
import mediaPlaceholderUrl from '../assets/media-placeholder.svg?no-inline'
import type {
  AiRecommendationStatus,
  MangaMetadataJob,
  MangaMetadataStats,
  MangaProfileJob,
  MangaProfileStats,
  MangaRecommendationResponse,
  Media
} from '../types'
import {
  EmptyState,
  PageHeader,
  SectionHeader,
  UiBadge,
  UiButton,
  UiCard,
  UiChip,
  UiIconButton,
  UiInput,
  UiSkeleton,
  controlClass,
  fieldLabelClass,
  popoverClass,
} from '../components/ui'
import { AsyncMediaDetail as MediaDetail } from '../components/asyncComponents'

// Search & filter state
const query = ref('')
const limit = ref(12)
const avoidInput = ref('')
const preferredInput = ref('')
const loading = ref(false)
const error = ref('')
const currentSeed = ref<number | undefined>(undefined)
const activePreset = ref<string>('guess')
const showAdvancedFilters = ref(false)
const showMaintenanceDrawer = ref(false)

// AI & DeepSeek configuration state
const statusLoading = ref(true)
const deepseekSaving = ref(false)
const deepseekApiKey = ref('')
const deepseekModel = ref('deepseek-chat')
const deepseekBaseUrl = ref('https://api.deepseek.com')
const deepseekMessage = ref('')
const modelInputRef = ref<HTMLInputElement | null>(null)
const showDeepSeekPanel = ref(false)
const settingsContainerRef = ref<HTMLElement | null>(null)

// Results & media selection
const result = ref<MangaRecommendationResponse | null>(null)
const aiStatus = ref<AiRecommendationStatus | null>(null)
const selectedMedia = ref<Media | null>(null)

// Batch maintenance job states
const metadataStats = ref<MangaMetadataStats | null>(null)
const metadataJob = ref<MangaMetadataJob | null>(null)
const metadataLoading = ref(false)
const profileStats = ref<MangaProfileStats | null>(null)
const profileJob = ref<MangaProfileJob | null>(null)
const profileLoading = ref(false)

// Discovery Presets
const discoveryPresets = [
  { id: 'guess', label: '猜你喜欢', desc: '根据常读画师与阅读习惯个性化推荐', query: '' },
  { id: 'random', label: '随心漫游', desc: '随机漫游探索未读书库', query: '' },
  { id: 'osananajimi', label: '青梅纯爱', desc: '幼驯染、甜蜜恋爱与温馨日常', query: '青梅竹马 纯爱' },
  { id: 'oneesan', label: '大姐姐', desc: '温柔年上与姐姐系作品', query: '大姐姐' },
  { id: 'short', label: '短篇精选', desc: '篇幅精炼、快节奏短篇', query: '短篇' },
  { id: 'long', label: '长篇剧情', desc: '长篇连载与丰富剧情', query: '长篇' },
  { id: 'color', label: '全彩精品', desc: '高质量全彩上色作品', query: '全彩' },
  { id: 'ba', label: '碧蓝档案', desc: '基沃托斯同人精选', query: '碧蓝档案' },
  { id: 'favorite_artists', label: '常读画师', desc: 'hahakigi、ねいさん等常读书籍', query: 'hahakigi' },
]

// Quick Inspiration Pills
const inspirationPills = [
  '青梅竹马', '大姐姐', '纯爱', '治愈', '妹妹', '女仆',
  '兔女郎', '辣妹', '催眠', '碧蓝档案', '原神',
  '短篇', '长篇', '全彩', 'hahakigi', 'ねいさん'
]

const deepseekModelOptions = [
  { id: 'deepseek-chat', label: 'deepseek-chat', description: '主推荐 (V3)' },
  { id: 'deepseek-reasoner', label: 'deepseek-reasoner', description: '深度推理 (R1)' },
]

const parseCsv = (value: string) => value
  .split(/[,，\n]/)
  .map(item => item.trim())
  .filter(Boolean)

const handleDocClick = (e: MouseEvent) => {
  if (showDeepSeekPanel.value && settingsContainerRef.value && !settingsContainerRef.value.contains(e.target as Node)) {
    showDeepSeekPanel.value = false
  }
}

const handleGlobalKeyDown = (e: KeyboardEvent) => {
  if (e.key === 'Escape' && showDeepSeekPanel.value) {
    showDeepSeekPanel.value = false
  }
}

onMounted(() => {
  document.addEventListener('pointerdown', handleDocClick)
  window.addEventListener('keydown', handleGlobalKeyDown)
})

onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', handleDocClick)
  window.removeEventListener('keydown', handleGlobalKeyDown)
})

const syncDeepSeekForm = (status: AiRecommendationStatus) => {
  deepseekModel.value = status.model || 'deepseek-chat'
  deepseekBaseUrl.value = status.base_url || 'https://api.deepseek.com'
}

const selectDeepSeekModel = (model: string) => {
  deepseekModel.value = model
}

const focusCustomModel = async () => {
  await nextTick()
  modelInputRef.value?.focus()
}

const fetchStatus = async () => {
  statusLoading.value = true
  try {
    const res = await axios.get<AiRecommendationStatus>(`${API_BASE_URL}/ai/recommendations/status`)
    aiStatus.value = res.data
    syncDeepSeekForm(res.data)
  } catch (err) {
    console.error('Failed to fetch AI recommendation status:', err)
  } finally {
    statusLoading.value = false
  }
}

const saveDeepSeekConfig = async () => {
  deepseekSaving.value = true
  deepseekMessage.value = ''
  try {
    const res = await axios.put<AiRecommendationStatus>(`${API_BASE_URL}/ai/recommendations/config`, {
      api_key: deepseekApiKey.value.trim() || undefined,
      model: deepseekModel.value.trim() || 'deepseek-chat',
      base_url: deepseekBaseUrl.value.trim() || 'https://api.deepseek.com',
    })
    aiStatus.value = res.data
    syncDeepSeekForm(res.data)
    deepseekApiKey.value = ''
    deepseekMessage.value = '已保存配置'
    window.setTimeout(() => {
      if (deepseekMessage.value === '已保存配置') deepseekMessage.value = ''
    }, 2000)
  } catch (err: any) {
    deepseekMessage.value = err?.response?.data?.detail || '保存失败'
  } finally {
    deepseekSaving.value = false
  }
}

const clearDeepSeekKey = async () => {
  if (!confirm('确定清除已保存的 DeepSeek API Key 吗？将切换回本地启发式推荐。')) return
  deepseekSaving.value = true
  deepseekMessage.value = ''
  try {
    const res = await axios.put<AiRecommendationStatus>(`${API_BASE_URL}/ai/recommendations/config`, {
      model: deepseekModel.value.trim() || 'deepseek-chat',
      base_url: deepseekBaseUrl.value.trim() || 'https://api.deepseek.com',
      clear_api_key: true,
    })
    aiStatus.value = res.data
    syncDeepSeekForm(res.data)
    deepseekApiKey.value = ''
    deepseekMessage.value = '已清除'
  } catch (err: any) {
    deepseekMessage.value = err?.response?.data?.detail || '清除失败'
  } finally {
    deepseekSaving.value = false
  }
}

const fetchProfileStats = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/recommend/manga-profiles/stats`)
    profileStats.value = res.data
  } catch (err) {
    console.error('Failed to fetch manga profile stats:', err)
  }
}

const fetchMetadataStats = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/recommend/manga-metadata/stats`)
    metadataStats.value = res.data
  } catch (err) {
    console.error('Failed to fetch manga metadata stats:', err)
  }
}

const pollMetadataJob = async (jobId: string) => {
  try {
    const res = await axios.get(`${API_BASE_URL}/recommend/manga-metadata/jobs/${jobId}`)
    metadataJob.value = res.data
    if (['queued', 'running'].includes(res.data.status)) {
      window.setTimeout(() => pollMetadataJob(jobId), 1200)
    } else {
      metadataLoading.value = false
      fetchMetadataStats()
    }
  } catch (err) {
    metadataLoading.value = false
    console.error('Failed to poll metadata job:', err)
  }
}

const startMetadataAnalysis = async (force = false) => {
  if (metadataLoading.value) return
  metadataLoading.value = true
  try {
    const res = await axios.post(`${API_BASE_URL}/recommend/manga-metadata/analyze`, {
      limit: 200,
      force,
    })
    metadataJob.value = res.data
    pollMetadataJob(res.data.job_id)
  } catch (err) {
    metadataLoading.value = false
    console.error('Failed to start metadata analysis:', err)
  }
}

const pollProfileJob = async (jobId: string) => {
  try {
    const res = await axios.get(`${API_BASE_URL}/recommend/manga-profiles/jobs/${jobId}`)
    profileJob.value = res.data
    if (['queued', 'running'].includes(res.data.status)) {
      window.setTimeout(() => pollProfileJob(jobId), 1500)
    } else {
      profileLoading.value = false
      fetchProfileStats()
    }
  } catch (err) {
    profileLoading.value = false
    console.error('Failed to poll profile job:', err)
  }
}

const startProfileAnalysis = async (force = false) => {
  if (profileLoading.value) return
  profileLoading.value = true
  try {
    const res = await axios.post(`${API_BASE_URL}/recommend/manga-profiles/analyze`, {
      limit: 50,
      sample_count: 10,
      force,
    })
    profileJob.value = res.data
    pollProfileJob(res.data.job_id)
  } catch (err) {
    profileLoading.value = false
    console.error('Failed to start profile analysis:', err)
  }
}

const requestRecommendations = async (customSeed?: number) => {
  if (loading.value) return
  loading.value = true
  error.value = ''
  if (customSeed !== undefined) {
    currentSeed.value = customSeed
  }
  try {
    const res = await axios.post(`${API_BASE_URL}/recommend/manga`, {
      query: query.value.trim(),
      limit: limit.value,
      avoid_tags: parseCsv(avoidInput.value),
      preferred_tags: parseCsv(preferredInput.value),
      seed: currentSeed.value,
    })
    result.value = res.data
  } catch (err: any) {
    error.value = err?.response?.data?.detail || '推荐获取失败，请重试'
  } finally {
    loading.value = false
  }
}

const reroll = () => {
  const nextSeed = Math.floor(Math.random() * 100000)
  requestRecommendations(nextSeed)
}

const applyPreset = (preset: typeof discoveryPresets[number]) => {
  activePreset.value = preset.id
  query.value = preset.query
  if (preset.id === 'random') {
    reroll()
  } else {
    currentSeed.value = undefined
    requestRecommendations()
  }
}

const applyPill = (pill: string) => {
  activePreset.value = 'custom'
  if (query.value.trim()) {
    if (!query.value.includes(pill)) {
      query.value = `${query.value.trim()} ${pill}`
    }
  } else {
    query.value = pill
  }
  currentSeed.value = undefined
  requestRecommendations()
}

const clearQuery = () => {
  query.value = ''
  activePreset.value = 'guess'
  currentSeed.value = undefined
  requestRecommendations()
}

const openReader = (media: Media) => {
  selectedMedia.value = media
}

const getViewStatusBadge = (status?: string) => {
  if (status === 'viewed') return { label: '已读', class: 'text-white/75' }
  if (status === 'viewing') return { label: '在读', class: 'text-white' }
  return { label: '未读', class: 'text-white' }
}

const coverSrc = (media: Media) => media.cover_path ? thumbnailUrl(media.cover_path) : mediaPlaceholderUrl
const onCoverError = (event: Event) => {
  const img = event.target as HTMLImageElement
  if (!img.src.endsWith(mediaPlaceholderUrl)) img.src = mediaPlaceholderUrl
}

const jobPercent = (job: { completed: number; total: number } | null) =>
  job?.total ? Math.round((job.completed / job.total) * 100) : 0

onMounted(() => {
  fetchStatus()
  fetchMetadataStats()
  fetchProfileStats()
  // Automatically load initial personalized recommendations on entry
  requestRecommendations()
})
</script>

<template>
  <div class="min-h-full">
    <PageHeader
      title="AI 漫画探索"
      :description="aiStatus?.deepseek_configured ? `DeepSeek 深度理解 · ${aiStatus.model}` : '阅读偏好与协同探索 · 本地快速规则'"
    >
      <template #actions>
        <div ref="settingsContainerRef" class="relative">
          <UiButton
            size="md"
            :aria-expanded="showDeepSeekPanel"
            aria-haspopup="dialog"
            title="配置 AI 模型"
            @click="showDeepSeekPanel = !showDeepSeekPanel"
          >
            <template #icon>
              <span class="size-2 rounded-full" :class="statusLoading ? 'bg-faint' : aiStatus?.deepseek_configured ? 'bg-success' : 'bg-warning'" aria-hidden="true"></span>
            </template>
            {{ statusLoading ? '检查中' : (aiStatus?.deepseek_configured ? 'DeepSeek' : '本地规则') }}
            <template #trailing>
              <ChevronDown :size="14" class="text-subtle transition-transform duration-150" :class="{ 'rotate-180': showDeepSeekPanel }" aria-hidden="true" />
            </template>
          </UiButton>

          <div
            v-if="showDeepSeekPanel"
            role="dialog"
            aria-label="DeepSeek 配置"
            :class="[popoverClass, 'absolute left-0 top-full z-50 mt-1.5 max-h-[80vh] sm:left-auto sm:right-0 w-[min(400px,calc(100vw-32px))] overflow-y-auto p-4']"
          >
            <div class="mb-4 flex items-start justify-between gap-3">
              <div class="min-w-0">
                <h2 class="text-body font-semibold text-ink">DeepSeek 配置</h2>
                <p class="mt-0.5 text-meta text-subtle">增强自然语言理解与推荐理由生成</p>
              </div>
              <UiBadge :tone="aiStatus?.deepseek_configured ? 'success' : 'neutral'">{{ aiStatus?.deepseek_configured ? '已连接' : '未配置' }}</UiBadge>
            </div>

            <div class="space-y-4">
              <label class="block">
                <span :class="fieldLabelClass">API Key</span>
                <UiInput
                  v-model="deepseekApiKey"
                  type="password"
                  :placeholder="aiStatus?.key_saved || aiStatus?.env_key_present ? '已配置，留空则保持不变' : 'sk-...'"
                  autocomplete="off"
                />
              </label>

              <div>
                <span :class="fieldLabelClass">预设模型</span>
                <div class="grid grid-cols-2 gap-2" role="radiogroup" aria-label="预设模型">
                  <button
                    v-for="opt in deepseekModelOptions"
                    :key="opt.id"
                    type="button"
                    role="radio"
                    :aria-checked="deepseekModel === opt.id"
                    class="rounded-lg border px-3 py-2 text-left transition-colors focus-ring"
                    :class="deepseekModel === opt.id ? 'border-accent/50 bg-accent/15' : 'border-line bg-surface-2 hover:border-line-strong'"
                    @click="selectDeepSeekModel(opt.id)"
                  >
                    <span class="flex items-center gap-1.5 truncate text-meta font-medium" :class="deepseekModel === opt.id ? 'text-accent-glow' : 'text-ink'">
                      {{ opt.label }}
                    </span>
                    <span class="mt-0.5 block text-caption text-subtle">{{ opt.description }}</span>
                  </button>
                </div>
              </div>

              <div>
                <div class="mb-1.5 flex items-center justify-between">
                  <label for="deepseek-model" class="text-meta font-medium text-muted">自定义 Model ID</label>
                  <button type="button" class="rounded-md px-1 text-caption text-subtle transition-colors hover:text-ink focus-ring" @click="focusCustomModel">手动编辑</button>
                </div>
                <input id="deepseek-model" ref="modelInputRef" v-model="deepseekModel" :class="controlClass('md')" placeholder="deepseek-chat" />
              </div>

              <label class="block">
                <span :class="fieldLabelClass">Base URL</span>
                <UiInput v-model="deepseekBaseUrl" placeholder="https://api.deepseek.com" />
              </label>
            </div>

            <div class="mt-4 flex items-center justify-between gap-3 border-t border-line-strong/70 pt-3">
              <span v-if="deepseekMessage" class="text-meta font-medium" :class="deepseekMessage.includes('失败') ? 'text-danger' : 'text-success'" role="status">
                {{ deepseekMessage }}
              </span>
              <span v-else class="text-caption text-subtle">未配置时自动使用本地快速规则</span>
              <div class="flex shrink-0 items-center gap-2">
                <UiButton v-if="aiStatus?.key_saved" size="sm" variant="ghost" :disabled="deepseekSaving" @click="clearDeepSeekKey">清除</UiButton>
                <UiButton size="sm" variant="primary" :loading="deepseekSaving" @click="saveDeepSeekConfig">
                  <template #icon><Save :size="14" aria-hidden="true" /></template>
                  保存
                </UiButton>
              </div>
            </div>
          </div>
        </div>
      </template>

      <div class="space-y-3">
        <div class="-mx-4 flex gap-2 overflow-x-auto px-4 scrollbar-none sm:-mx-6 sm:px-6 lg:mx-0 lg:flex-wrap lg:px-0" role="group" aria-label="探索模式">
          <UiChip
            v-for="preset in discoveryPresets"
            :key="preset.id"
            :selected="activePreset === preset.id"
            :title="preset.desc"
            @click="applyPreset(preset)"
          >
            <template v-if="preset.id === 'guess' || preset.id === 'random' || preset.id === 'favorite_artists'" #leading>
              <Compass v-if="preset.id === 'guess' || preset.id === 'random'" :size="14" aria-hidden="true" />
              <Star v-else :size="14" aria-hidden="true" />
            </template>
            {{ preset.label }}
          </UiChip>
        </div>

        <div class="flex items-center gap-2">
          <UiInput
            v-model="query"
            type="search"
            size="lg"
            class="flex-1"
            aria-label="描述想看的漫画"
            placeholder="题材、画师、氛围、篇幅，如：青梅竹马 纯爱"
            @keydown.enter="requestRecommendations()"
          >
            <template #leading><Search :size="16" /></template>
            <template v-if="query" #trailing>
              <UiIconButton label="清空" size="sm" @click="clearQuery"><X :size="14" aria-hidden="true" /></UiIconButton>
            </template>
          </UiInput>
          <UiButton variant="primary" size="lg" :loading="loading" aria-label="探索推荐" @click="requestRecommendations()">
            <template #icon><Sparkles :size="16" aria-hidden="true" /></template>
            <span class="hidden sm:inline">探索推荐</span>
          </UiButton>
          <UiIconButton
            label="偏好与过滤"
            variant="secondary"
            size="lg"
            :pressed="showAdvancedFilters"
            @click="showAdvancedFilters = !showAdvancedFilters"
          >
            <SlidersHorizontal :size="18" aria-hidden="true" />
          </UiIconButton>
        </div>

        <div class="-mx-4 flex items-center gap-1.5 overflow-x-auto px-4 scrollbar-none sm:-mx-6 sm:px-6 lg:mx-0 lg:flex-wrap lg:px-0" role="group" aria-label="灵感标签">
          <span class="mr-1 shrink-0 text-meta text-subtle">灵感</span>
          <button
            v-for="pill in inspirationPills"
            :key="pill"
            type="button"
            class="inline-flex h-7 shrink-0 items-center whitespace-nowrap rounded-md px-2 text-meta text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-ring pointer-coarse:h-9"
            @click="applyPill(pill)"
          >
            <span class="text-faint" aria-hidden="true">#</span>{{ pill }}
          </button>
        </div>

        <div v-if="showAdvancedFilters" class="grid grid-cols-1 gap-3 rounded-2xl border border-line bg-surface p-4 sm:grid-cols-3">
          <label class="block">
            <span :class="fieldLabelClass">优先标签</span>
            <UiInput v-model="preferredInput" placeholder="逗号分隔，如：短篇, 治愈" />
          </label>
          <label class="block">
            <span :class="fieldLabelClass">排除标签</span>
            <UiInput v-model="avoidInput" placeholder="逗号分隔，如：黑暗, 触手" />
          </label>
          <label class="block">
            <span :class="fieldLabelClass">返回数量</span>
            <select v-model.number="limit" :class="[controlClass('md'), 'select-native']">
              <option :value="8">8 本精选</option>
              <option :value="12">12 本标准</option>
              <option :value="18">18 本扩充</option>
              <option :value="24">24 本全览</option>
            </select>
          </label>
        </div>
      </div>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container space-y-10">
        <section>
          <SectionHeader title="推荐书目" :count="result ? `${result.recommendations.length} 本` : undefined">
            <template #actions>
              <UiButton v-if="result?.recommendations.length" variant="ghost" size="sm" :disabled="loading" title="换一批推荐" @click="reroll">
                <template #icon><RefreshCw :size="14" :class="{ 'animate-spin': loading }" aria-hidden="true" /></template>
                换一批
              </UiButton>
            </template>
          </SectionHeader>

          <div v-if="error" role="alert" class="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">
            <AlertTriangle :size="16" class="mt-0.5 shrink-0" aria-hidden="true" />
            <span>{{ error }}</span>
          </div>

          <div v-else-if="loading" class="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3" aria-busy="true">
            <UiCard v-for="i in limit" :key="i" padding="sm" class="flex gap-4">
              <UiSkeleton class="aspect-[2/3] w-24 shrink-0 rounded-lg sm:w-28" />
              <div class="flex-1 space-y-2.5 py-1">
                <UiSkeleton shape="text" class="w-4/5" />
                <UiSkeleton shape="text" class="w-1/2" />
                <UiSkeleton shape="text" class="w-full" />
              </div>
            </UiCard>
          </div>

          <div v-else-if="result?.recommendations.length" class="grid grid-cols-1 gap-4 lg:grid-cols-2 2xl:grid-cols-3">
            <UiCard
              v-for="item in result.recommendations"
              :key="item.media.id"
              as="article"
              padding="sm"
              class="group flex gap-4 transition-colors duration-150 hover:border-line-strong"
            >
              <button
                type="button"
                class="relative aspect-[2/3] w-24 shrink-0 self-start overflow-hidden rounded-lg bg-surface-2 focus-ring sm:w-28"
                :aria-label="`阅读 ${item.media.title}`"
                @click="openReader(item.media)"
              >
                <img :src="coverSrc(item.media)" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.03]" @error="onCoverError" />
                <span class="pointer-events-none absolute inset-0 rounded-lg ring-1 ring-inset ring-white/8"></span>
                <span
                  class="absolute left-1.5 top-1.5 inline-flex h-6 items-center rounded-md bg-black/60 px-1.5 text-caption font-medium"
                  :class="getViewStatusBadge(item.media.view_status).class"
                >
                  {{ getViewStatusBadge(item.media.view_status).label }}
                </span>
              </button>

              <div class="flex min-w-0 flex-1 flex-col">
                <button type="button" class="text-left focus-ring rounded-md" @click="openReader(item.media)">
                  <h3 class="line-clamp-2 text-body font-medium leading-snug text-ink" :title="item.media.title">
                    {{ item.media.title }}
                  </h3>
                </button>
                <p class="mt-1.5 line-clamp-3 text-meta text-muted">{{ item.reason }}</p>
                <div v-if="item.matched_tags.length" class="mt-2 flex flex-wrap gap-1">
                  <UiBadge v-for="tag in item.matched_tags.slice(0, 3)" :key="tag" class="max-w-[120px] truncate">{{ tag }}</UiBadge>
                </div>
                <div class="mt-auto flex items-center justify-between gap-2 pt-3">
                  <p class="flex items-center gap-2 text-caption text-subtle tabular-nums">
                    <span v-if="item.media.page_count">{{ item.media.page_count }} 页</span>
                    <span v-if="item.media.rating" class="inline-flex items-center gap-0.5"><Star :size="12" class="text-star" fill="currentColor" aria-hidden="true" />{{ item.media.rating }}</span>
                  </p>
                  <UiButton size="sm" title="立即阅读" @click="openReader(item.media)">
                    <template #icon><BookOpen :size="14" aria-hidden="true" /></template>
                    阅读
                  </UiButton>
                </div>
              </div>
            </UiCard>
          </div>

          <div v-else class="rounded-2xl border border-dashed border-line">
            <EmptyState
              :icon="Sparkles"
              title="未找到完全契合的书目"
              :description="result?.message || '试试上面的灵感标签，或点「猜你喜欢」浏览馆藏新作。'"
            >
              <UiButton variant="primary" size="sm" @click="clearQuery">返回猜你喜欢</UiButton>
              <UiButton size="sm" @click="reroll">随机探索</UiButton>
            </EmptyState>
          </div>
        </section>

        <section class="rounded-2xl border border-line bg-surface">
          <button
            type="button"
            class="flex w-full items-center gap-3 rounded-2xl px-4 py-3.5 text-left transition-colors hover:bg-surface-2 focus-ring-inset sm:px-5"
            :aria-expanded="showMaintenanceDrawer"
            @click="showMaintenanceDrawer = !showMaintenanceDrawer"
          >
            <Layers :size="16" class="shrink-0 text-subtle" aria-hidden="true" />
            <span class="min-w-0 flex-1">
              <span class="block truncate text-body font-medium text-ink">图书画像与后台维护</span>
              <span class="block truncate text-meta text-subtle tabular-nums">元数据画像 {{ metadataStats?.profiled ?? 0 }} · 视觉画像 {{ profileStats?.profiled ?? 0 }}</span>
            </span>
            <span class="hidden text-meta text-subtle sm:inline">{{ showMaintenanceDrawer ? '收起' : '展开' }}</span>
            <ChevronDown :size="16" class="shrink-0 text-subtle transition-transform duration-150" :class="{ 'rotate-180': showMaintenanceDrawer }" aria-hidden="true" />
          </button>

          <div v-if="showMaintenanceDrawer" class="grid grid-cols-1 gap-4 border-t border-line p-4 sm:p-5 md:grid-cols-2">
            <div
              v-for="panel in [
                { key: 'metadata', title: '元数据画像', desc: '从标题、画师与站点条目提取结构化标签', stats: metadataStats, job: metadataJob, busy: metadataLoading, refresh: fetchMetadataStats, start: startMetadataAnalysis },
                { key: 'profile', title: '内容视觉画像', desc: '抽样漫画页面提取色彩风格与视觉氛围', stats: profileStats, job: profileJob, busy: profileLoading, refresh: fetchProfileStats, start: startProfileAnalysis },
              ]"
              :key="panel.key"
              class="space-y-3 rounded-lg bg-surface-2 p-4"
            >
              <div class="flex items-start justify-between gap-3">
                <div class="min-w-0">
                  <h3 class="text-body font-medium text-ink">{{ panel.title }}</h3>
                  <p class="mt-0.5 text-meta text-subtle">{{ panel.desc }}</p>
                </div>
                <UiIconButton label="刷新" size="sm" @click="panel.refresh()"><RefreshCw :size="14" aria-hidden="true" /></UiIconButton>
              </div>

              <dl class="grid grid-cols-3 gap-2">
                <div>
                  <dt class="text-caption text-subtle">已画像</dt>
                  <dd class="text-heading font-semibold text-ink tabular-nums">{{ panel.stats?.profiled ?? 0 }}</dd>
                </div>
                <div>
                  <dt class="text-caption text-subtle">待分析</dt>
                  <dd class="text-heading font-semibold text-ink tabular-nums">{{ panel.stats?.missing ?? 0 }}</dd>
                </div>
                <div>
                  <dt class="text-caption text-subtle">需更新</dt>
                  <dd class="text-heading font-semibold text-ink tabular-nums">{{ panel.stats?.stale ?? 0 }}</dd>
                </div>
              </dl>

              <div v-if="panel.job" class="space-y-1.5">
                <div class="flex justify-between gap-2 text-caption text-muted">
                  <span class="truncate">{{ panel.job.message || panel.job.status }}</span>
                  <span class="shrink-0 tabular-nums">{{ panel.job.completed }} / {{ panel.job.total }}</span>
                </div>
                <div class="h-1 overflow-hidden rounded-sm bg-surface-3">
                  <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: `${jobPercent(panel.job)}%` }"></div>
                </div>
              </div>

              <div class="flex flex-wrap gap-2">
                <UiButton size="sm" :loading="panel.busy" @click="panel.start(false)">分析增量</UiButton>
                <UiButton size="sm" variant="ghost" :disabled="panel.busy" @click="panel.start(true)">强制重新分析</UiButton>
              </div>
            </div>
          </div>
        </section>
      </div>
    </div>

    <MediaDetail
      v-if="selectedMedia"
      :initial-media="selectedMedia"
      :all-media="result?.recommendations.map(item => item.media) || []"
      @close="selectedMedia = null"
      @updated="selectedMedia = $event"
      @navigate="selectedMedia = $event"
    />
  </div>
</template>
