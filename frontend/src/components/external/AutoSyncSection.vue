<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue'
import axios from 'axios'
import { Clock, Play, RefreshCw, AlertTriangle, CheckCircle, XCircle, Loader2, ChevronDown } from 'lucide-vue-next'
import { API_BASE_URL } from '../../config'
import { UiButton, fieldLabelClass, menuItemClass, popoverClass } from '../ui'
import type { AutoSyncLogEntry } from '../../types'

const props = defineProps<{
  sourceType: 'wnacg' | 'x'
  sourceId: number | null
  enabled: boolean
  intervalHours: number
  lastRunAt: string | null
  nextRunAt: string | null
  lastStatus: string | null
  lastMessage: string | null
  canEnable: boolean        // cookie + download path both set
  disableReason?: string    // reason if canEnable is false
}>()

const emit = defineEmits<{
  (e: 'update', payload: { auto_sync_enabled?: boolean; auto_sync_interval_hours?: number }): void
}>()



const triggering = ref(false)
const triggerError = ref('')
const logs = ref<AutoSyncLogEntry[]>([])
const logsExpanded = ref(false)
const intervalDropdownOpen = ref(false)

const currentIntervalLabel = computed(() => {
  const opt = intervalOptions.find(o => o.value === props.intervalHours)
  return opt ? opt.label : `${props.intervalHours} 小时`
})

const selectInterval = (value: number) => {
  emit('update', { auto_sync_interval_hours: value })
  intervalDropdownOpen.value = false
}

const intervalOptions = [
  { value: 6, label: '每 6 小时' },
  { value: 12, label: '每 12 小时' },
  { value: 24, label: '每天' },
  { value: 48, label: '每 2 天' },
  { value: 72, label: '每 3 天' },
]

const statusIcon = computed(() => {
  switch (props.lastStatus) {
    case 'success': return CheckCircle
    case 'failed': return XCircle
    case 'partial': return AlertTriangle
    case 'running': return Loader2
    default: return Clock
  }
})

const statusColor = computed(() => {
  switch (props.lastStatus) {
    case 'success': return 'text-success'
    case 'failed': return 'text-danger'
    case 'partial': return 'text-warning'
    case 'running': return 'text-info'
    default: return 'text-subtle'
  }
})

const statusLabel = computed(() => {
  switch (props.lastStatus) {
    case 'success': return '成功'
    case 'failed': return '失败'
    case 'partial': return '部分成功'
    case 'running': return '运行中'
    default: return '未运行'
  }
})

const logDotClass = (status: string) => (
  status === 'success' ? 'bg-success' : status === 'failed' ? 'bg-danger' : 'bg-warning'
)

const countdown = ref('')
let countdownTimer: ReturnType<typeof setInterval> | null = null

const updateCountdown = () => {
  if (!props.enabled || !props.nextRunAt) {
    countdown.value = ''
    return
  }
  const next = new Date(props.nextRunAt + (props.nextRunAt.endsWith('Z') ? '' : 'Z'))
  const diff = next.getTime() - Date.now()
  if (diff <= 0) {
    countdown.value = '即将执行'
    return
  }
  const hours = Math.floor(diff / 3600000)
  const minutes = Math.floor((diff % 3600000) / 60000)
  if (hours > 0) {
    countdown.value = `${hours}h ${minutes}m 后执行`
  } else {
    countdown.value = `${minutes}m 后执行`
  }
}

const formatTime = (value: string | null) => {
  if (!value) return '-'
  const d = new Date(value + (value.endsWith('Z') ? '' : 'Z'))
  return d.toLocaleString()
}

const formatDuration = (seconds: number | null) => {
  if (!seconds) return '-'
  if (seconds < 60) return `${seconds}s`
  const m = Math.floor(seconds / 60)
  const s = seconds % 60
  return `${m}m ${s}s`
}

const toggleEnabled = () => {
  if (!props.canEnable && !props.enabled) return
  emit('update', { auto_sync_enabled: !props.enabled })
}



const triggerNow = async () => {
  if (!props.sourceId || triggering.value) return
  triggering.value = true
  triggerError.value = ''
  try {
    await axios.post(`${API_BASE_URL}/auto-sync/${props.sourceType}/${props.sourceId}/trigger`)
  } catch (err: any) {
    triggerError.value = err.response?.data?.detail || '触发失败'
  } finally {
    triggering.value = false
  }
}

const fetchLogs = async () => {
  if (!props.sourceId) return
  try {
    const res = await axios.get(`${API_BASE_URL}/auto-sync/logs`, {
      params: { source_type: props.sourceType, source_id: props.sourceId, limit: 10 },
    })
    logs.value = res.data
  } catch (err) {
    console.error('Failed to fetch auto-sync logs:', err)
  }
}

const toggleLogs = () => {
  logsExpanded.value = !logsExpanded.value
  if (logsExpanded.value && logs.value.length === 0) {
    fetchLogs()
  }
}

let pollTimer: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  updateCountdown()
  countdownTimer = setInterval(updateCountdown, 30000)
  // Poll status every 30s when running
  pollTimer = setInterval(() => {
    if (props.lastStatus === 'running' && logsExpanded.value) {
      fetchLogs()
    }
  }, 30000)
})

onUnmounted(() => {
  if (countdownTimer) clearInterval(countdownTimer)
  if (pollTimer) clearInterval(pollTimer)
})

watch(() => props.nextRunAt, updateCountdown)
watch(() => props.sourceId, () => {
  logs.value = []
  logsExpanded.value = false
})
</script>

<template>
  <div class="space-y-3 border-t border-line pt-5">
    <div class="flex items-center justify-between gap-3">
      <div class="min-w-0">
        <p class="flex items-center gap-2 text-body font-medium text-ink">
          <Clock :size="15" class="text-subtle" aria-hidden="true" />
          自动同步并下载
        </p>
        <p v-if="!enabled && !lastStatus && !canEnable" class="mt-0.5 text-caption text-subtle">
          {{ disableReason || '请先设置 Cookie 和下载路径' }}
        </p>
      </div>
      <button
        type="button"
        role="switch"
        :aria-checked="enabled"
        aria-label="自动同步并下载"
        :disabled="!canEnable && !enabled"
        :title="!canEnable && !enabled ? (disableReason || '请先配置 Cookie 和下载路径') : (enabled ? '关闭' : '开启')"
        class="relative h-6 w-10 shrink-0 rounded-full transition-colors focus-ring disabled:cursor-not-allowed disabled:opacity-45"
        :class="enabled ? 'bg-accent' : 'bg-surface-3 ring-1 ring-inset ring-line-strong'"
        @click="toggleEnabled"
      >
        <span class="absolute left-1 top-1 size-4 rounded-full bg-white transition-transform" :class="enabled ? 'translate-x-4' : ''" />
      </button>
    </div>

    <template v-if="enabled || lastStatus">
      <div v-if="enabled" class="flex items-center gap-3">
        <span :class="[fieldLabelClass, 'mb-0 shrink-0']">间隔</span>
        <div class="relative flex-1">
          <button
            type="button"
            :aria-expanded="intervalDropdownOpen"
            aria-haspopup="listbox"
            class="flex h-8 w-full items-center justify-between rounded-lg border border-line bg-surface-2 px-2.5 text-left text-meta text-ink transition-colors hover:border-line-strong focus-ring"
            @click="intervalDropdownOpen = !intervalDropdownOpen"
          >
            <span>{{ currentIntervalLabel }}</span>
            <ChevronDown :size="14" :class="intervalDropdownOpen ? 'rotate-180' : ''" class="text-subtle transition-transform" aria-hidden="true" />
          </button>
          <div v-if="intervalDropdownOpen" role="listbox" :class="[popoverClass, 'absolute left-0 top-full z-50 mt-1.5 max-h-60 w-full overflow-y-auto']">
            <button
              v-for="opt in intervalOptions"
              :key="opt.value"
              type="button"
              role="option"
              :aria-selected="intervalHours === opt.value"
              :class="[menuItemClass, intervalHours === opt.value ? 'font-medium text-ink' : '']"
              @click="selectInterval(opt.value)"
            >
              {{ opt.label }}
            </button>
          </div>
        </div>
      </div>

      <div class="space-y-1 rounded-lg bg-surface-2 px-3 py-2.5">
        <div class="flex items-center justify-between gap-2">
          <div class="flex items-center gap-1.5">
            <component :is="statusIcon" :size="14" :class="[statusColor, lastStatus === 'running' ? 'animate-spin' : '']" aria-hidden="true" />
            <span class="text-meta font-medium" :class="statusColor">{{ statusLabel }}</span>
          </div>
          <span v-if="lastRunAt" class="text-caption text-subtle tabular-nums">{{ formatTime(lastRunAt) }}</span>
        </div>
        <p v-if="lastMessage" class="text-caption text-muted">{{ lastMessage }}</p>
        <p v-if="enabled && countdown" class="text-caption text-subtle tabular-nums">下次：{{ countdown }}</p>
      </div>

      <div class="flex gap-2">
        <UiButton size="sm" class="flex-1" :loading="triggering" :disabled="lastStatus === 'running' || !sourceId" @click="triggerNow">
          <template #icon><Play :size="14" aria-hidden="true" /></template>
          {{ triggering ? '触发中' : '立即执行' }}
        </UiButton>
        <UiButton size="sm" variant="ghost" :aria-expanded="logsExpanded" @click="toggleLogs">
          <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
          日志
        </UiButton>
      </div>

      <p v-if="triggerError" role="alert" class="rounded-lg border border-danger/25 bg-danger/10 px-3 py-2 text-caption text-danger">
        {{ triggerError }}
      </p>

      <div v-if="logsExpanded" class="space-y-2">
        <div class="flex items-center justify-between">
          <span class="text-caption font-medium text-subtle">执行历史</span>
          <button type="button" class="rounded-md px-1.5 text-caption text-subtle transition-colors hover:text-ink focus-ring" @click="fetchLogs">刷新</button>
        </div>
        <p v-if="logs.length === 0" class="py-3 text-center text-caption text-subtle">暂无执行记录</p>
        <ul v-else class="divide-y divide-line overflow-hidden rounded-lg border border-line">
          <li v-for="log in logs" :key="log.id" class="space-y-0.5 px-3 py-2 text-caption">
            <div class="flex items-center justify-between gap-2">
              <div class="flex items-center gap-1.5">
                <span class="inline-block size-1.5 rounded-full" :class="logDotClass(log.status)" aria-hidden="true" />
                <span class="text-muted tabular-nums">{{ formatTime(log.started_at) }}</span>
              </div>
              <span class="text-subtle tabular-nums">{{ formatDuration(log.duration_seconds) }}</span>
            </div>
            <div class="flex gap-3 text-subtle tabular-nums">
              <span v-if="log.synced_count">同步 {{ log.synced_count }}</span>
              <span v-if="log.downloaded_count">下载 {{ log.downloaded_count }}</span>
              <span v-if="log.failed_count" class="text-danger">失败 {{ log.failed_count }}</span>
            </div>
            <p v-if="log.message" class="truncate text-subtle">{{ log.message }}</p>
          </li>
        </ul>
      </div>
    </template>
  </div>
</template>
