<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import axios from 'axios'
import {
  AlertTriangle,
  BookOpen,
  ChevronDown,
  ChevronUp,
  Compass,
  KeyRound,
  Layers,
  Loader2,
  RefreshCw,
  Save,
  Search,
  ShieldCheck,
  SlidersHorizontal,
  Sparkles,
  Star,
  X
} from 'lucide-vue-next'
import { API_BASE_URL } from '../config'
import type {
  AiRecommendationStatus,
  MangaMetadataJob,
  MangaMetadataStats,
  MangaProfileJob,
  MangaProfileStats,
  MangaRecommendationResponse,
  Media
} from '../types'
import MediaCard from '../components/MediaCard.vue'
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
  if (status === 'viewed') {
    return { label: '已读', class: 'bg-slate-500/20 text-slate-300 border-slate-500/30' }
  }
  if (status === 'viewing') {
    return { label: '在读', class: 'bg-amber-500/20 text-amber-300 border-amber-500/30' }
  }
  return { label: '未读', class: 'bg-emerald-500/20 text-emerald-300 border-emerald-500/30' }
}

onMounted(() => {
  fetchStatus()
  fetchMetadataStats()
  fetchProfileStats()
  // Automatically load initial personalized recommendations on entry
  requestRecommendations()
})
</script>

<template>
  <div class="min-h-screen text-white pb-20">
    <!-- Top Header Bar -->
    <header class="border-b border-white/10 bg-surface/50 backdrop-blur-xl sticky top-0 z-40 px-4 md:px-8 py-3.5">
      <div class="flex items-center justify-between gap-4 max-w-7xl mx-auto">
        <div class="flex items-center gap-3 min-w-0">
          <div class="w-10 h-10 rounded-2xl bg-gradient-to-tr from-accent/30 to-purple-500/20 border border-accent/40 flex items-center justify-center text-accent shrink-0 shadow-lg shadow-accent/10">
            <Sparkles :size="20" class="animate-pulse" />
          </div>
          <div class="min-w-0">
            <h1 class="text-xl md:text-2xl font-black text-white tracking-tight flex items-center gap-2">
              AI 漫画探索
            </h1>
            <p class="text-[11px] text-white/50 truncate">
              {{ aiStatus?.deepseek_configured ? `DeepSeek 深度理解 · ${aiStatus.model}` : '阅读偏好与协同探索 · 本地极速引擎' }}
            </p>
          </div>
        </div>

        <div class="flex items-center gap-2.5">
          <!-- DeepSeek Config Popover Button -->
          <div ref="settingsContainerRef" class="relative">
            <button
              type="button"
              @click="showDeepSeekPanel = !showDeepSeekPanel"
              :class="aiStatus?.deepseek_configured ? 'border-emerald-400/30 text-emerald-300 bg-emerald-500/10 hover:bg-emerald-500/20' : 'border-amber-400/30 text-amber-300 bg-amber-500/10 hover:bg-amber-500/20'"
              class="h-9 px-3 rounded-xl border text-xs font-bold flex items-center gap-1.5 transition-all active:scale-95"
              title="配置 AI 模型"
            >
              <ShieldCheck v-if="aiStatus?.deepseek_configured" :size="14" />
              <AlertTriangle v-else :size="14" />
              <span class="hidden sm:inline">{{ statusLoading ? '检查中' : (aiStatus?.deepseek_configured ? 'DeepSeek' : '本地规则') }}</span>
              <ChevronDown :size="13" class="transition-transform duration-200" :class="{ 'rotate-180': showDeepSeekPanel }" />
            </button>

            <!-- DeepSeek Settings Flyout -->
            <div
              v-if="showDeepSeekPanel"
              class="absolute right-0 top-11 z-50 w-[calc(100vw-2rem)] sm:w-[420px] max-h-[85vh] overflow-y-auto rounded-2xl border border-white/15 bg-background/95 p-5 shadow-2xl shadow-black/80 backdrop-blur-2xl animate-in fade-in zoom-in-95 duration-150"
            >
              <div class="flex items-start justify-between gap-4 mb-4">
                <div class="flex items-center gap-3">
                  <div class="w-9 h-9 rounded-xl bg-accent/15 border border-accent/25 flex items-center justify-center text-accent shrink-0">
                    <KeyRound :size="18" />
                  </div>
                  <div>
                    <h2 class="text-base font-black text-white">DeepSeek 配置</h2>
                    <p class="text-[11px] text-white/40">增强自然语言理解与推荐理由生成</p>
                  </div>
                </div>
                <div
                  :class="aiStatus?.deepseek_configured ? 'border-emerald-400/30 text-emerald-300 bg-emerald-400/10' : 'border-white/10 text-white/40 bg-white/5'"
                  class="px-2.5 py-1 rounded-lg border text-[10px] font-bold shrink-0"
                >
                  {{ aiStatus?.deepseek_configured ? '已连接' : '未配置' }}
                </div>
              </div>

              <div class="space-y-3.5">
                <div>
                  <label class="block text-xs font-bold text-white/60 mb-1.5">API Key</label>
                  <input
                    v-model="deepseekApiKey"
                    type="password"
                    class="w-full rounded-xl border border-white/10 bg-black/30 px-3.5 py-2 text-xs text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-accent/50"
                    :placeholder="aiStatus?.key_saved || aiStatus?.env_key_present ? '已配置，留空则保持不变' : 'sk-...'"
                    autocomplete="off"
                  />
                </div>

                <div>
                  <label class="block text-xs font-bold text-white/60 mb-1.5">预设模型</label>
                  <div class="grid grid-cols-2 gap-2">
                    <button
                      v-for="opt in deepseekModelOptions"
                      :key="opt.id"
                      type="button"
                      @click="selectDeepSeekModel(opt.id)"
                      :class="deepseekModel === opt.id ? 'border-accent bg-accent/20 text-white font-bold' : 'border-white/10 bg-black/20 text-white/60 hover:text-white hover:bg-white/5'"
                      class="px-3 py-2 rounded-xl border text-left text-xs transition-all"
                    >
                      <div class="font-bold truncate">{{ opt.label }}</div>
                      <div class="text-[10px] text-white/40 mt-0.5">{{ opt.description }}</div>
                    </button>
                  </div>
                </div>

                <div>
                  <div class="flex items-center justify-between mb-1.5">
                    <label class="text-xs font-bold text-white/60">自定义 Model ID</label>
                    <button
                      type="button"
                      @click="focusCustomModel"
                      class="text-[10px] text-accent hover:underline"
                    >
                      手动编辑
                    </button>
                  </div>
                  <input
                    ref="modelInputRef"
                    v-model="deepseekModel"
                    class="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-accent/50"
                    placeholder="deepseek-chat"
                  />
                </div>

                <div>
                  <label class="block text-xs font-bold text-white/60 mb-1.5">Base URL</label>
                  <input
                    v-model="deepseekBaseUrl"
                    class="w-full rounded-xl border border-white/10 bg-black/30 px-3 py-2 text-xs text-white focus:outline-none focus:ring-2 focus:ring-accent/50"
                    placeholder="https://api.deepseek.com"
                  />
                </div>
              </div>

              <div class="mt-4 pt-3 border-t border-white/10 flex items-center justify-between gap-3">
                <span
                  v-if="deepseekMessage"
                  class="text-xs font-bold"
                  :class="deepseekMessage.includes('失败') ? 'text-rose-400' : 'text-emerald-400'"
                >
                  {{ deepseekMessage }}
                </span>
                <span v-else class="text-[11px] text-white/35">未配置时自动使用本地快速规则</span>

                <div class="flex items-center gap-2 shrink-0">
                  <button
                    v-if="aiStatus?.key_saved"
                    @click="clearDeepSeekKey"
                    :disabled="deepseekSaving"
                    class="h-8 px-2.5 rounded-lg border border-white/10 bg-white/5 text-xs text-white/60 hover:text-white hover:bg-white/10"
                  >
                    清除
                  </button>
                  <button
                    @click="saveDeepSeekConfig"
                    :disabled="deepseekSaving"
                    class="h-8 px-3.5 rounded-lg bg-accent text-white text-xs font-bold flex items-center gap-1.5 hover:brightness-110 active:scale-95"
                  >
                    <Loader2 v-if="deepseekSaving" :size="13" class="animate-spin" />
                    <Save v-else :size="13" />
                    保存
                  </button>
                </div>
              </div>
            </div>
          </div>

          <!-- Reroll Button in Header -->
          <button
            @click="reroll"
            :disabled="loading"
            class="h-9 px-3 rounded-xl border border-white/10 bg-white/5 text-white/80 hover:text-white hover:bg-white/10 flex items-center gap-1.5 text-xs font-bold transition-all active:scale-95 disabled:opacity-40"
            title="换一批推荐"
          >
            <RefreshCw :size="13" :class="{ 'animate-spin': loading }" />
            <span>换一批</span>
          </button>
        </div>
      </div>
    </header>

    <!-- Main Container -->
    <main class="max-w-7xl mx-auto px-4 md:px-8 pt-6 space-y-6">
      <!-- Hero Exploration Section -->
      <section class="rounded-3xl border border-white/10 bg-surface/40 p-5 md:p-6 backdrop-blur-xl shadow-2xl shadow-black/20 space-y-4">
        <!-- Preset Mode Tabs -->
        <div class="flex items-center gap-1.5 overflow-x-auto pb-1 scrollbar-none">
          <button
            v-for="preset in discoveryPresets"
            :key="preset.id"
            @click="applyPreset(preset)"
            :class="activePreset === preset.id ? 'bg-accent text-white shadow-lg shadow-accent/25 border-accent' : 'bg-white/5 text-white/65 hover:bg-white/10 hover:text-white border-white/10'"
            class="px-3.5 py-1.5 rounded-xl border text-xs font-bold whitespace-nowrap transition-all active:scale-95 flex items-center gap-1.5"
            :title="preset.desc"
          >
            <Compass v-if="preset.id === 'guess' || preset.id === 'random'" :size="13" />
            <Star v-else-if="preset.id === 'favorite_artists'" :size="13" />
            <span>{{ preset.label }}</span>
          </button>
        </div>

        <!-- Big Search Prompt Bar -->
        <div class="relative flex items-center gap-2">
          <div class="relative flex-1">
            <div class="absolute left-4 top-1/2 -translate-y-1/2 text-white/35 pointer-events-none">
              <Search :size="18" />
            </div>
            <input
              v-model="query"
              @keydown.enter="requestRecommendations()"
              type="text"
              class="w-full h-12 md:h-14 rounded-2xl border border-white/15 bg-black/40 pl-11 pr-10 text-sm md:text-base text-white placeholder-white/35 focus:outline-none focus:ring-2 focus:ring-accent/50 transition-all"
              placeholder="输入题材、画师、氛围、篇幅（例如：青梅竹马 纯爱、大姐姐、短篇、hahakigi...）"
            />
            <button
              v-if="query"
              @click="clearQuery"
              class="absolute right-3.5 top-1/2 -translate-y-1/2 w-6 h-6 rounded-full bg-white/10 hover:bg-white/20 text-white/60 hover:text-white flex items-center justify-center transition-all"
              title="清空"
            >
              <X :size="13" />
            </button>
          </div>

          <button
            @click="requestRecommendations()"
            :disabled="loading"
            class="h-12 md:h-14 px-5 md:px-7 rounded-2xl bg-gradient-to-r from-accent to-purple-600 text-white text-sm font-black flex items-center gap-2 hover:brightness-110 active:scale-95 disabled:opacity-40 transition-all shadow-lg shadow-accent/20 shrink-0"
          >
            <Loader2 v-if="loading" :size="18" class="animate-spin" />
            <Sparkles v-else :size="18" />
            <span class="hidden sm:inline">探索推荐</span>
          </button>

          <button
            @click="showAdvancedFilters = !showAdvancedFilters"
            :class="showAdvancedFilters ? 'bg-accent/20 border-accent/40 text-accent' : 'bg-white/5 border-white/10 text-white/60 hover:bg-white/10 hover:text-white'"
            class="h-12 md:h-14 w-12 md:w-14 rounded-2xl border flex items-center justify-center transition-all shrink-0"
            title="偏好与过滤"
          >
            <SlidersHorizontal :size="18" />
          </button>
        </div>

        <!-- Quick Inspiration Pills -->
        <div class="flex flex-wrap items-center gap-2 pt-1">
          <span class="text-[11px] font-bold text-white/40 mr-1 flex items-center gap-1">
            <Sparkles :size="11" /> 灵感标签:
          </span>
          <button
            v-for="pill in inspirationPills"
            :key="pill"
            @click="applyPill(pill)"
            class="px-2.5 py-1 rounded-lg border border-white/8 bg-white/[0.04] text-[11px] font-medium text-white/70 hover:border-accent/40 hover:bg-accent/10 hover:text-accent transition-all active:scale-95"
          >
            {{ pill }}
          </button>
        </div>

        <!-- Collapsible Advanced Filters -->
        <div v-if="showAdvancedFilters" class="pt-3 border-t border-white/10 grid grid-cols-1 sm:grid-cols-3 gap-3 animate-in fade-in duration-200">
          <div>
            <label class="block text-xs font-bold text-white/60 mb-1.5">优先标签 (逗号分隔)</label>
            <input
              v-model="preferredInput"
              class="w-full h-9 rounded-xl border border-white/10 bg-black/30 px-3 text-xs text-white placeholder-white/30 focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="例如：短篇, 治愈"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-white/60 mb-1.5">排除避雷 (逗号分隔)</label>
            <input
              v-model="avoidInput"
              class="w-full h-9 rounded-xl border border-white/10 bg-black/30 px-3 text-xs text-white placeholder-white/30 focus:outline-none focus:ring-1 focus:ring-accent"
              placeholder="例如：黑暗, 触手"
            />
          </div>
          <div>
            <label class="block text-xs font-bold text-white/60 mb-1.5">返回结果数量</label>
            <select
              v-model.number="limit"
              class="w-full h-9 rounded-xl border border-white/10 bg-black/30 px-3 text-xs text-white focus:outline-none focus:ring-1 focus:ring-accent"
            >
              <option :value="8">8 本精选</option>
              <option :value="12">12 本标准</option>
              <option :value="18">18 本扩充</option>
              <option :value="24">24 本全览</option>
            </select>
          </div>
        </div>
      </section>

      <!-- Results Grid Section -->
      <section class="space-y-4">
        <div class="flex items-center justify-between gap-4">
          <div class="flex items-center gap-2">
            <h2 class="text-lg md:text-xl font-black text-white">推荐书目</h2>
            <span v-if="result" class="px-2.5 py-0.5 rounded-full bg-white/10 border border-white/10 text-xs font-bold text-white/70">
              {{ result.recommendations.length }} 本
            </span>
          </div>
          <div class="flex items-center gap-2">
            <button
              v-if="result?.recommendations.length"
              @click="reroll"
              :disabled="loading"
              class="h-8 px-3 rounded-xl border border-white/10 bg-white/5 text-xs font-bold text-white/75 hover:bg-white/10 hover:text-white flex items-center gap-1.5 transition-all"
            >
              <RefreshCw :size="12" :class="{ 'animate-spin': loading }" />
              <span>换一批</span>
            </button>
          </div>
        </div>

        <!-- Error State -->
        <div v-if="error" class="rounded-2xl border border-rose-400/20 bg-rose-500/10 p-5 text-rose-200 text-sm flex items-center gap-3">
          <AlertTriangle :size="18" class="text-rose-400 shrink-0" />
          <span>{{ error }}</span>
        </div>

        <!-- Loading Skeleton -->
        <div v-else-if="loading" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <div
            v-for="i in limit"
            :key="i"
            class="h-44 rounded-2xl border border-white/5 bg-white/[0.03] animate-pulse flex p-3.5 gap-4"
          >
            <div class="w-28 h-full rounded-xl bg-white/5 shrink-0"></div>
            <div class="flex-1 space-y-3 py-1">
              <div class="h-4 bg-white/5 rounded w-3/4"></div>
              <div class="h-3 bg-white/5 rounded w-1/2"></div>
              <div class="h-10 bg-white/5 rounded w-full"></div>
            </div>
          </div>
        </div>

        <!-- Recommendations Bento Cards -->
        <div v-else-if="result?.recommendations.length" class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
          <article
            v-for="item in result.recommendations"
            :key="item.media.id"
            class="group relative flex rounded-2xl border border-white/10 bg-surface/50 hover:bg-surface/80 hover:border-accent/40 p-3.5 transition-all duration-200 shadow-lg shadow-black/10 hover:shadow-xl hover:shadow-accent/5"
          >
            <!-- Left: Cover with MediaCard & Status Badge -->
            <div class="relative w-28 shrink-0 cursor-pointer overflow-hidden rounded-xl" @click="openReader(item.media)">
              <MediaCard :media="item.media" class="h-full w-full object-cover group-hover:scale-105 transition-transform duration-300" />
              <!-- Status Badge on Cover -->
              <span
                :class="getViewStatusBadge(item.media.view_status).class"
                class="absolute top-1.5 left-1.5 px-1.5 py-0.5 rounded-md border text-[9px] font-black backdrop-blur-md"
              >
                {{ getViewStatusBadge(item.media.view_status).label }}
              </span>
            </div>

            <!-- Right: Metadata & Recommendation Info -->
            <div class="min-w-0 flex-1 pl-3.5 flex flex-col justify-between">
              <div>
                <!-- Title -->
                <button
                  @click="openReader(item.media)"
                  class="text-left w-full cursor-pointer group-hover:text-accent transition-colors"
                >
                  <h3 class="text-sm font-black text-white leading-snug line-clamp-2" :title="item.media.title">
                    {{ item.media.title }}
                  </h3>
                </button>

                <!-- Recommendation Reason -->
                <p class="text-[11px] leading-relaxed text-white/70 mt-2 line-clamp-2 bg-black/20 rounded-lg p-2 border border-white/5">
                  {{ item.reason }}
                </p>

                <!-- Matched Tags / Keywords -->
                <div v-if="item.matched_tags.length" class="mt-2 flex flex-wrap gap-1">
                  <span
                    v-for="tag in item.matched_tags.slice(0, 3)"
                    :key="tag"
                    class="px-1.5 py-0.5 rounded-md bg-accent/15 border border-accent/25 text-[10px] font-bold text-accent truncate max-w-[120px]"
                  >
                    {{ tag }}
                  </span>
                </div>
              </div>

              <!-- Footer with Meta & Actions -->
              <div class="mt-3 pt-2 border-t border-white/8 flex items-center justify-between text-[11px]">
                <div class="flex items-center gap-2 text-white/45">
                  <span v-if="item.media.page_count">{{ item.media.page_count }}P</span>
                  <span v-if="item.media.rating" class="flex items-center gap-0.5 text-amber-300">
                    <Star :size="10" fill="currentColor" /> {{ item.media.rating }}
                  </span>
                </div>

                <div class="flex items-center gap-1.5">
                  <button
                    @click="openReader(item.media)"
                    class="h-7 px-2.5 rounded-lg bg-accent text-white font-bold text-xs flex items-center gap-1 hover:brightness-110 active:scale-95 transition-all shadow-sm shadow-accent/20"
                    title="立即阅读"
                  >
                    <BookOpen :size="12" />
                    <span>阅读</span>
                  </button>
                </div>
              </div>
            </div>
          </article>
        </div>

        <!-- Empty Results Message -->
        <div v-else class="rounded-3xl border border-white/10 bg-surface/30 min-h-[360px] flex flex-col items-center justify-center text-center p-8">
          <div class="w-16 h-16 rounded-3xl bg-white/5 border border-white/10 flex items-center justify-center text-white/30 mb-4">
            <Sparkles :size="28" />
          </div>
          <h3 class="text-base font-black text-white/80">未找到完全契合的书目</h3>
          <p class="text-xs text-white/40 mt-1.5 max-w-sm">
            {{ result?.message || '试着尝试上面的灵感标签，或点击“猜你喜欢”浏览馆藏新作。' }}
          </p>
          <div class="mt-5 flex gap-2">
            <button
              @click="clearQuery"
              class="px-4 py-2 rounded-xl bg-accent text-white text-xs font-bold hover:brightness-110 active:scale-95 transition-all"
            >
              返回猜你喜欢
            </button>
            <button
              @click="reroll"
              class="px-4 py-2 rounded-xl border border-white/10 bg-white/5 text-xs font-bold text-white/70 hover:bg-white/10 hover:text-white transition-all"
            >
              随机探索
            </button>
          </div>
        </div>
      </section>

      <!-- Bottom Maintenance Accordion (Collapsed by Default) -->
      <section class="rounded-2xl border border-white/10 bg-surface/30 backdrop-blur-md overflow-hidden">
        <button
          type="button"
          @click="showMaintenanceDrawer = !showMaintenanceDrawer"
          class="w-full px-5 py-3.5 flex items-center justify-between text-left hover:bg-white/[0.02] transition-colors"
        >
          <div class="flex items-center gap-2.5">
            <Layers :size="15" class="text-white/40" />
            <span class="text-xs font-bold text-white/70">图书画像分析与后台维护</span>
            <span class="text-[10px] text-white/40">
              ({{ metadataStats?.profiled ?? 0 }} 元数据已画像 · {{ profileStats?.profiled ?? 0 }} 视觉画像)
            </span>
          </div>
          <div class="flex items-center gap-2 text-white/40">
            <span class="text-[11px]">{{ showMaintenanceDrawer ? '收起' : '展开管理' }}</span>
            <ChevronUp v-if="showMaintenanceDrawer" :size="14" />
            <ChevronDown v-else :size="14" />
          </div>
        </button>

        <div v-if="showMaintenanceDrawer" class="p-5 border-t border-white/8 grid grid-cols-1 md:grid-cols-2 gap-5 animate-in fade-in duration-200">
          <!-- Metadata Profile Card -->
          <div class="rounded-xl border border-white/8 bg-black/20 p-4 space-y-3">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-sm font-bold text-white">元数据画像</h3>
                <p class="text-[11px] text-white/40">从标题、画师与站点条目提取结构化标签</p>
              </div>
              <button
                @click="fetchMetadataStats"
                class="w-7 h-7 rounded-lg border border-white/10 bg-white/5 text-white/50 hover:text-white flex items-center justify-center"
                title="刷新"
              >
                <RefreshCw :size="13" />
              </button>
            </div>

            <div class="grid grid-cols-3 gap-2 text-center py-1">
              <div class="bg-white/5 rounded-lg p-2">
                <div class="text-base font-black text-white">{{ metadataStats?.profiled ?? 0 }}</div>
                <div class="text-[10px] text-white/40">已画像</div>
              </div>
              <div class="bg-white/5 rounded-lg p-2">
                <div class="text-base font-black text-white">{{ metadataStats?.missing ?? 0 }}</div>
                <div class="text-[10px] text-white/40">待分析</div>
              </div>
              <div class="bg-white/5 rounded-lg p-2">
                <div class="text-base font-black text-white">{{ metadataStats?.stale ?? 0 }}</div>
                <div class="text-[10px] text-white/40">需更新</div>
              </div>
            </div>

            <div v-if="metadataJob" class="rounded-lg border border-white/8 bg-white/5 p-2.5 text-xs text-white/70 space-y-1.5">
              <div class="flex justify-between text-[11px]">
                <span class="font-bold">{{ metadataJob.message || metadataJob.status }}</span>
                <span>{{ metadataJob.completed }} / {{ metadataJob.total }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-white/10 overflow-hidden">
                <div
                  class="h-full bg-accent transition-all duration-300"
                  :style="{ width: `${metadataJob.total ? Math.round((metadataJob.completed / metadataJob.total) * 100) : 0}%` }"
                ></div>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2 pt-1">
              <button
                @click="startMetadataAnalysis(false)"
                :disabled="metadataLoading"
                class="h-8 rounded-lg bg-white/5 border border-white/10 text-xs font-bold text-white/70 hover:text-white hover:bg-white/10 flex items-center justify-center gap-1.5 disabled:opacity-40"
              >
                <Loader2 v-if="metadataLoading" :size="13" class="animate-spin" />
                <span>分析增量</span>
              </button>
              <button
                @click="startMetadataAnalysis(true)"
                :disabled="metadataLoading"
                class="h-8 rounded-lg bg-white/5 border border-white/10 text-xs font-bold text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-40"
              >
                强制重新分析
              </button>
            </div>
          </div>

          <!-- Content Profile Card -->
          <div class="rounded-xl border border-white/8 bg-black/20 p-4 space-y-3">
            <div class="flex items-center justify-between">
              <div>
                <h3 class="text-sm font-bold text-white">内容视觉画像</h3>
                <p class="text-[11px] text-white/40">抽样漫画页面提取色彩风格与视觉氛围</p>
              </div>
              <button
                @click="fetchProfileStats"
                class="w-7 h-7 rounded-lg border border-white/10 bg-white/5 text-white/50 hover:text-white flex items-center justify-center"
                title="刷新"
              >
                <RefreshCw :size="13" />
              </button>
            </div>

            <div class="grid grid-cols-3 gap-2 text-center py-1">
              <div class="bg-white/5 rounded-lg p-2">
                <div class="text-base font-black text-white">{{ profileStats?.profiled ?? 0 }}</div>
                <div class="text-[10px] text-white/40">已画像</div>
              </div>
              <div class="bg-white/5 rounded-lg p-2">
                <div class="text-base font-black text-white">{{ profileStats?.missing ?? 0 }}</div>
                <div class="text-[10px] text-white/40">待分析</div>
              </div>
              <div class="bg-white/5 rounded-lg p-2">
                <div class="text-base font-black text-white">{{ profileStats?.stale ?? 0 }}</div>
                <div class="text-[10px] text-white/40">需更新</div>
              </div>
            </div>

            <div v-if="profileJob" class="rounded-lg border border-white/8 bg-white/5 p-2.5 text-xs text-white/70 space-y-1.5">
              <div class="flex justify-between text-[11px]">
                <span class="font-bold">{{ profileJob.message || profileJob.status }}</span>
                <span>{{ profileJob.completed }} / {{ profileJob.total }}</span>
              </div>
              <div class="h-1.5 rounded-full bg-white/10 overflow-hidden">
                <div
                  class="h-full bg-accent transition-all duration-300"
                  :style="{ width: `${profileJob.total ? Math.round((profileJob.completed / profileJob.total) * 100) : 0}%` }"
                ></div>
              </div>
            </div>

            <div class="grid grid-cols-2 gap-2 pt-1">
              <button
                @click="startProfileAnalysis(false)"
                :disabled="profileLoading"
                class="h-8 rounded-lg bg-white/5 border border-white/10 text-xs font-bold text-white/70 hover:text-white hover:bg-white/10 flex items-center justify-center gap-1.5 disabled:opacity-40"
              >
                <Loader2 v-if="profileLoading" :size="13" class="animate-spin" />
                <span>分析增量</span>
              </button>
              <button
                @click="startProfileAnalysis(true)"
                :disabled="profileLoading"
                class="h-8 rounded-lg bg-white/5 border border-white/10 text-xs font-bold text-white/70 hover:text-white hover:bg-white/10 disabled:opacity-40"
              >
                强制重新分析
              </button>
            </div>
          </div>
        </div>
      </section>
    </main>

    <!-- Interactive Reader & Media Detail Modal -->
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

<style scoped>
.scrollbar-none::-webkit-scrollbar {
  display: none;
}
.scrollbar-none {
  -ms-overflow-style: none;
  scrollbar-width: none;
}
</style>
