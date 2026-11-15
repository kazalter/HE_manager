<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref } from 'vue'
import axios from 'axios'
import { API_BASE_URL } from '../config'
import ThemeSelect from './ThemeSelect.vue'
import { SectionHeader, UiButton, UiCard } from './ui'

interface MetadataCoverageStats {
  total_media: number
  tagged_media: number
  total_tags: number
  with_artist: number
  manga_total: number
  manga_profiled: number
  manga_wnacg_total: number
  manga_wnacg_with_sidecar: number
  audio_total: number
  audio_with_sidecar: number
}

interface ExternalBackfillJob {
  job_id: string
  status: string
  total: number
  completed: number
  failed: number
  tags_attached: number
  current_title: string
  message: string
}

const SCOPE_OPTIONS = [
  { value: 'all', label: 'WNACG + ASMR' },
  { value: 'wnacg', label: '仅 WNACG' },
  { value: 'asmr', label: '仅 ASMR' },
]

const LIMIT_OPTIONS = [
  { value: 50, label: '单批 50 项' },
  { value: 100, label: '单批 100 项' },
  { value: 300, label: '单批 300 项' },
]

const stats = ref<MetadataCoverageStats | null>(null)
const loadingStats = ref(false)
const runningLocal = ref(false)
const externalJob = ref<ExternalBackfillJob | null>(null)
const startingExternal = ref(false)
const externalScope = ref<'all' | 'wnacg' | 'asmr'>('all')
const externalLimit = ref<number>(100)
const statusMessage = ref('')
const errorMessage = ref('')
let pollTimer: number | undefined

const isExternalRunning = () =>
  Boolean(externalJob.value && ['queued', 'preparing', 'running'].includes(externalJob.value.status))

async function loadStats() {
  loadingStats.value = true
  errorMessage.value = ''
  try {
    const res = await axios.get<MetadataCoverageStats>(`${API_BASE_URL}/system/metadata/stats`)
    stats.value = res.data
  } catch {
    errorMessage.value = '无法读取元数据覆盖率统计'
  } finally {
    loadingStats.value = false
  }
}

async function runLocalBackfill() {
  if (runningLocal.value) return
  runningLocal.value = true
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    const res = await axios.post(`${API_BASE_URL}/system/backfill-metadata`, null, {
      params: { limit: 10000 },
    })
    if (res.data?.stats) {
      stats.value = res.data.stats
    } else {
      await loadStats()
    }
    const d = res.data || {}
    const noiseSuffix = (d.noise_tags_deleted ?? 0) > 0 || (d.noise_links_removed ?? 0) > 0
      ? `，清理噪声标签 ${d.noise_tags_deleted ?? 0} 个`
      : ''
    statusMessage.value = `已检查 ${d.checked ?? 0} 项，更新 ${d.updated ?? 0} 项（新增标签 ${d.tags_attached ?? 0} 条，补全作者 ${d.artist_filled ?? 0} 项，漫画档案 ${d.manga_profiles_created ?? 0} 份${noiseSuffix}）。`
  } catch (err: any) {
    errorMessage.value = err?.response?.data?.detail || '本地元数据补充失败，请稍后重试。'
  } finally {
    runningLocal.value = false
  }
}

async function pollExternalJob(jobId: string) {
  window.clearTimeout(pollTimer)
  try {
    const res = await axios.get<ExternalBackfillJob>(`${API_BASE_URL}/system/backfill-external-metadata/${jobId}`)
    externalJob.value = res.data
    if (['queued', 'preparing', 'running'].includes(res.data.status)) {
      pollTimer = window.setTimeout(() => pollExternalJob(jobId), 1500)
    } else {
      statusMessage.value = res.data.message || '外部详情抓取已完成'
      await loadStats()
    }
  } catch {
    errorMessage.value = '查询外部详情抓取进度失败'
  }
}

async function startExternalBackfill() {
  if (startingExternal.value || isExternalRunning()) return
  startingExternal.value = true
  errorMessage.value = ''
  statusMessage.value = ''
  try {
    const res = await axios.post<ExternalBackfillJob>(`${API_BASE_URL}/system/backfill-external-metadata`, null, {
      params: {
        limit: externalLimit.value,
        delay_seconds: 1.0,
        include_wnacg: externalScope.value !== 'asmr',
        include_asmr: externalScope.value !== 'wnacg',
      },
    })
    externalJob.value = res.data
    if (['queued', 'preparing', 'running'].includes(res.data.status)) {
      pollTimer = window.setTimeout(() => pollExternalJob(res.data.job_id), 1200)
    } else {
      statusMessage.value = res.data.message || '没有需要补充详情的作品'
      await loadStats()
    }
  } catch (err: any) {
    errorMessage.value = err?.response?.data?.detail || '启动外部详情抓取失败，请检查代理与网络。'
  } finally {
    startingExternal.value = false
  }
}

async function cancelExternalBackfill() {
  if (!externalJob.value || !isExternalRunning()) return
  try {
    const res = await axios.post<ExternalBackfillJob>(
      `${API_BASE_URL}/system/backfill-external-metadata/${externalJob.value.job_id}/cancel`,
    )
    externalJob.value = res.data
  } catch {
    errorMessage.value = '取消抓取任务失败'
  }
}

onMounted(loadStats)
onBeforeUnmount(() => {
  window.clearTimeout(pollTimer)
})
</script>

<template>
  <section>
    <SectionHeader
      title="元数据与标签索引"
      description="入库时自动提取标题作者、社团、原作、X 推文作者与 #标签；可随时补充存量本地元数据（含噪声标签清理）或限速抓取 WNACG / ASMR 详情标签。"
    />
    <UiCard padding="md" class="space-y-4">
      <div v-if="stats" class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <div class="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
          <p class="text-caption text-subtle">已打标媒体</p>
          <p class="mt-0.5 text-body font-medium text-ink tabular-nums">
            {{ stats.tagged_media }} / {{ stats.total_media }}
          </p>
        </div>
        <div class="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
          <p class="text-caption text-subtle">已识别作者</p>
          <p class="mt-0.5 text-body font-medium text-ink tabular-nums">
            {{ stats.with_artist }} / {{ stats.total_media }}
          </p>
        </div>
        <div class="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
          <p class="text-caption text-subtle">漫画档案</p>
          <p class="mt-0.5 text-body font-medium text-ink tabular-nums">
            {{ stats.manga_profiled }} / {{ stats.manga_total }}
          </p>
        </div>
        <div class="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
          <p class="text-caption text-subtle">WNACG 详情缓存</p>
          <p class="mt-0.5 text-body font-medium text-ink tabular-nums">
            {{ stats.manga_wnacg_with_sidecar }} / {{ stats.manga_wnacg_total }}
          </p>
        </div>
        <div class="rounded-lg border border-line bg-surface-2 px-3 py-2.5">
          <p class="text-caption text-subtle">ASMR 详情缓存</p>
          <p class="mt-0.5 text-body font-medium text-ink tabular-nums">
            {{ stats.audio_with_sidecar ?? 0 }} / {{ stats.audio_total ?? 0 }}
          </p>
        </div>
      </div>

      <div class="flex flex-wrap items-center gap-3">
        <UiButton variant="primary" :loading="runningLocal" :disabled="runningLocal" @click="runLocalBackfill">
          {{ runningLocal ? '补充中…' : '一键补充本地元数据' }}
        </UiButton>
        <ThemeSelect v-model="externalScope" :options="SCOPE_OPTIONS" class="w-36 shrink-0" />
        <ThemeSelect v-model="externalLimit" :options="LIMIT_OPTIONS" class="w-32 shrink-0" />
        <UiButton
          variant="secondary"
          :loading="startingExternal || isExternalRunning()"
          :disabled="startingExternal || isExternalRunning() || runningLocal"
          @click="startExternalBackfill"
        >
          {{ isExternalRunning() ? '抓取详情中…' : '抓取 WNACG / ASMR 详情标签' }}
        </UiButton>
        <UiButton v-if="isExternalRunning()" variant="ghost" @click="cancelExternalBackfill">
          取消抓取
        </UiButton>
        <UiButton variant="secondary" :disabled="loadingStats || runningLocal" @click="loadStats">
          刷新统计
        </UiButton>
        <span v-if="stats" class="text-caption text-subtle tabular-nums">有效标签共 {{ stats.total_tags }} 个</span>
      </div>

      <div
        v-if="externalJob && isExternalRunning()"
        class="rounded-lg border border-line bg-surface-2 px-3 py-2.5 text-meta text-muted"
      >
        <p class="tabular-nums">
          进度：{{ externalJob.completed + externalJob.failed }} / {{ externalJob.total }}（成功 {{ externalJob.completed }}，失败 {{ externalJob.failed }}，新增标签 {{ externalJob.tags_attached }}）
        </p>
        <p v-if="externalJob.current_title" class="mt-0.5 truncate text-caption text-subtle">
          {{ externalJob.current_title }}
        </p>
      </div>

      <p v-if="statusMessage" role="status" class="text-meta text-muted">{{ statusMessage }}</p>
      <p v-if="errorMessage" role="alert" class="text-meta text-danger">{{ errorMessage }}</p>
    </UiCard>
  </section>
</template>
