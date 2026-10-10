<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { UiButton, UiCard } from '../ui'
import {
  confirmProposal,
  rejectProposal,
  getJob,
  utcTime,
  AssistantApiError,
} from '../../utils/assistantApi'
import type { ProposalDTO, JobDTO } from '../../types/assistant'
const props = withDefaults(
  defineProps<{ proposal: ProposalDTO; enabled?: boolean }>(),
  { enabled: true },
)
const emit = defineEmits<{ changed: [] }>()
const state = ref(props.proposal.state),
  job = ref<JobDTO | null>(props.proposal.result?.job ?? null),
  busy = ref(false),
  error = ref(''),
  stale = ref(false),
  now = ref(Date.now())
const controller = new AbortController()
let alive = true,
  timer: ReturnType<typeof setTimeout> | undefined
const clock = setInterval(() => {
  now.value = Date.now()
}, 1000)
const expired = computed(
  () =>
    !Number.isFinite(utcTime(props.proposal.expires_at)) ||
    utcTime(props.proposal.expires_at) <= now.value,
)
const incomplete = computed(
  () =>
    props.proposal.kind === 'media_update' &&
    (props.proposal.before.tags_truncated === true ||
      props.proposal.after.tags_truncated === true) &&
    (!Array.isArray(props.proposal.after.add_tags) ||
      !Array.isArray(props.proposal.after.remove_tags)),
)
const actionable = computed(
  () =>
    props.enabled &&
    state.value === 'pending' &&
    !expired.value &&
    !stale.value &&
    !busy.value &&
    !incomplete.value,
)
const stateLabels: Record<string, string> = {
  pending: '待确认',
  applied: '已执行',
  queued: '已安排扫描',
  rejected: '已拒绝',
  expired: '已过期',
  stale: '资料已变化',
}
const status = computed(() =>
  state.value === 'pending' && expired.value
    ? '已过期'
    : stateLabels[state.value] || '建议不可用',
)
const jobLabels: Record<string, string> = {
  queued: '扫描等待中',
  running: '正在扫描',
  completed: '扫描完成',
  failed: '扫描失败',
  interrupted: '扫描已中断',
}
const labels: Record<string, string> = {
  rating: '评分',
  favorite: '收藏',
  source_url: '来源链接',
  tags: '标签',
  display_name: '目录',
  status: '状态',
  mode: '扫描范围',
  partial_warning: '扫描说明',
  add_tags: '新增标签',
  remove_tags: '移除标签',
  tags_truncated: '标签预览',
  folder_id: '目录编号',
  scan_mode: '扫描范围',
  action: '操作',
  notice: '说明',
}
function formatValue(name: string, value: unknown): string {
  if (name === 'tags_truncated')
    return value ? '仅展示前 50 个标签；本次增删见变更清单' : '完整'
  if (name === 'action' && value === 'scan') return '扫描'
  if (name === 'scan_mode' && value === 'auto') return '自动识别'
  if (Array.isArray(value))
    return (
      value
        .map((item) => {
          if (
            item &&
            typeof item === 'object' &&
            typeof item.name === 'string'
          ) {
            const group =
              item.namespace && item.namespace !== 'general'
                ? String(item.namespace) + '：'
                : ''
            return group + item.name
          }
          return formatValue('', item)
        })
        .join('、') || '无'
    )
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (value === null) return '清空'
  if (typeof value === 'object')
    return Object.entries(value as Record<string, unknown>)
      .map(
        ([key, item]) => (labels[key] || key) + '：' + formatValue(key, item),
      )
      .join('；')
  return String(value)
}
function preview(value: Record<string, unknown>) {
  return Object.entries(value)
    .map(
      ([name, data]) => (labels[name] || name) + '：' + formatValue(name, data),
    )
    .join('\n')
}

async function act(confirm: boolean) {
  if (!actionable.value) return
  busy.value = true
  error.value = ''
  try {
    if (confirm) {
      const result = await confirmProposal(
        props.proposal.id,
        props.proposal.payload_hash,
        { signal: controller.signal },
      )
      if (!alive) return
      state.value = result.state
      job.value = result.job ?? null
      if (result.job_id) void pollJob(result.job_id)
    } else {
      const result = await rejectProposal(props.proposal.id, {
        signal: controller.signal,
      })
      if (!alive) return
      state.value = result.state
    }
    emit('changed')
  } catch (c) {
    if (alive) {
      stale.value = c instanceof AssistantApiError && c.status === 409
      error.value = stale.value
        ? '资料已变化或建议不可用，请重新生成建议。'
        : '操作暂不可用，请重新连接后核实状态。'
    }
  } finally {
    if (alive) busy.value = false
  }
}
async function pollJob(id: string) {
  if (
    !alive ||
    (job.value &&
      ['completed', 'failed', 'interrupted'].includes(job.value.status))
  )
    return
  try {
    const value = await getJob(id, { signal: controller.signal })
    if (!alive) return
    job.value = value
    error.value = ''
  } catch {
    if (alive) error.value = '扫描状态暂不可用，稍后重试；不会重复启动扫描。'
  }
  if (
    alive &&
    (!job.value ||
      !['completed', 'failed', 'interrupted'].includes(job.value.status))
  )
    timer = setTimeout(() => {
      void pollJob(id)
    }, 2000)
}
watch(
  () => props.proposal,
  (p) => {
    state.value = p.state
    if (p.result?.job) job.value = p.result.job
  },
  { deep: true },
)
if (props.proposal.result?.job_id) void pollJob(props.proposal.result.job_id)
onBeforeUnmount(() => {
  alive = false
  controller.abort()
  clearInterval(clock)
  clearTimeout(timer)
})
</script>
<template>
  <UiCard class="min-w-0 space-y-3 [overflow-wrap:anywhere]" padding="sm">
    <div class="flex flex-wrap items-center justify-between gap-2">
      <h3 class="font-semibold text-ink">
        {{ proposal.kind === 'scan' ? '扫描建议' : '资料整理建议' }}
      </h3>
      <span class="rounded-full bg-surface-2 px-3 py-1 text-sm text-muted">{{
        status
      }}</span>
    </div>
    <p class="font-medium text-ink">
      {{ proposal.target_label }}
      <span class="text-sm text-muted">#{{ proposal.target_id }}</span>
    </p>
    <div class="grid min-w-0 gap-3 sm:grid-cols-2">
      <div class="min-w-0 rounded-xl bg-surface-2 p-3">
        <h4 class="mb-2 text-sm font-medium text-muted">当前资料</h4>
        <pre
          class="whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink [overflow-wrap:anywhere]"
          >{{ preview(proposal.before) }}</pre
        >
      </div>
      <div class="min-w-0 rounded-xl border border-accent/30 bg-accent/5 p-3">
        <h4 class="mb-2 text-sm font-medium text-muted">拟议变更</h4>
        <pre
          class="whitespace-pre-wrap font-sans text-sm leading-relaxed text-ink [overflow-wrap:anywhere]"
          >{{ preview(proposal.after) }}</pre
        >
      </div>
    </div>
    <p v-if="state === 'pending' && !expired" class="text-sm text-muted">
      有效期至
      {{
        new Date(utcTime(proposal.expires_at)).toLocaleTimeString()
      }}。确认后才会执行。
    </p>
    <p v-if="incomplete" role="alert" class="text-sm text-danger">
      旧建议的标签变更预览不完整，请重新生成建议。
    </p>
    <p v-if="proposal.kind === 'scan'" class="text-sm text-muted">
      扫描可能逐步处理文件；停止聊天不会停止已确认的扫描。
    </p>
    <div class="flex flex-wrap gap-3">
      <UiButton
        data-confirm
        class="min-h-11"
        variant="primary"
        :disabled="!actionable"
        :loading="busy"
        @click="act(true)"
        >{{ proposal.kind === 'scan' ? '确认启动扫描' : '确认修改' }}</UiButton
      ><UiButton
        data-reject
        class="min-h-11"
        :disabled="!actionable"
        @click="act(false)"
        >拒绝</UiButton
      >
    </div>
    <p v-if="job" role="status" class="text-sm text-muted">
      {{ jobLabels[job.status] || '扫描状态待核实' }} · {{ job.job_id
      }}<br v-if="job.message" /><span v-if="job.message">{{
        job.message
      }}</span>
    </p>
    <p v-if="error" role="alert" class="text-sm text-danger">{{ error }}</p>
  </UiCard>
</template>
