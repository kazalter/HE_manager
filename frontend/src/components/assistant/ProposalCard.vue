<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { UiButton, UiCard } from '../ui'
import {
  confirmProposal,
  rejectProposal,
  getJob,
  utcTime,
  AssistantApiError,
  assistantErrorText,
  selectProposalTargets,
  getProposalTargets,
  notifyApprovalChanged,
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
const batchItems = computed(() => props.proposal.kind === 'media_batch_update' && Array.isArray(props.proposal.before.items) ? props.proposal.before.items as { media_id: number; title?: string }[] : [])
const selection = ref<number[]>(batchItems.value.map(x => x.media_id))
const selectionDirty = computed(() => batchItems.value.length > 0 && (selection.value.length !== batchItems.value.length || batchItems.value.some(x => !selection.value.includes(x.media_id))))
const affected = ref<Record<string, unknown>[]>([]), affectedMore = ref(false), affectedOpen = ref(false), affectedBusy = ref(false)
const kindLabels: Record<string, string> = { media_update: '修改媒体资料', media_batch_update: '批量修改资料', tag_rename: '标签改名', tag_merge: '合并标签', scan: '扫描目录', maintenance: '维护任务', file_move: '文件改名 / 移动' }
const confirmLabel = computed(() => ({ scan: '批准启动扫描', maintenance: '批准启动任务', file_move: '批准移动', tag_merge: '批准合并', tag_rename: '批准改名' })[props.proposal.kind as 'scan'] || '批准修改')
async function saveSelection() {
  if (!selection.value.length || busy.value || expired.value || state.value !== 'pending') return
  busy.value = true; error.value = ''
  try {
    await selectProposalTargets(props.proposal.id, selection.value, { signal: controller.signal })
    if (!alive) return
    state.value = 'stale'; notifyApprovalChanged(); emit('changed')
  } catch (e) { if (alive) error.value = assistantErrorText(e) }
  finally { if (alive) busy.value = false }
}
async function loadAffected(append = false) {
  if (affectedBusy.value) return
  affectedBusy.value = true; affectedOpen.value = true
  try {
    const page = await getProposalTargets(props.proposal.id, { offset: append ? affected.value.length : 0, signal: controller.signal })
    if (!alive) return
    affected.value = append ? [...affected.value, ...page.items] : page.items; affectedMore.value = page.has_more
  } catch (e) { if (alive) error.value = assistantErrorText(e) }
  finally { if (alive) affectedBusy.value = false }
}
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
  queued: '等待执行',
  running: '正在执行',
  completed: '执行完成',
  failed: '执行失败',
  interrupted: '执行中断',
  needs_recovery: '需要恢复',
}
const labels: Record<string, string> = {
  title: '标题', artist: '作者', view_status: '阅读 / 观看状态', items: '变更清单', media_id: '媒体编号', source_path: '源路径', destination_path: '目标路径', file_count: '文件项数', path_changes: '关联路径变更', fields: '资料', affected_media_count: '影响媒体数', affected_media_ids: '媒体编号', affected_list_truncated: '清单已截断', changes_truncated: '清单已截断', source_tag: '原标签', target_tag: '目标标签', namespace: '分类', name: '名称', media_count: '媒体数', media_ids: '媒体编号', list_truncated: '清单已截断',
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
  if (name === 'view_status') return ({ unviewed: '未看', viewing: '正在看', viewed: '已看' } as Record<string, string>)[String(value)] || String(value)
  if (name === 'action') return ({ recheck_missing: '复查缺失文件', recheck_duplicates: '复查重复媒体', regenerate_thumbnail: '重建缩略图', backup_database: '数据库备份' } as Record<string, string>)[String(value)] || String(value)
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
  if (!actionable.value || (confirm && selectionDirty.value)) return
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
    notifyApprovalChanged()
    emit('changed')
  } catch (c) {
    if (alive) {
      stale.value = c instanceof AssistantApiError && ['assistant_proposal_stale', 'assistant_proposal_expired', 'assistant_proposal_consumed', 'assistant_proposal_unavailable'].includes(c.code)
      error.value = stale.value
        ? '资料已变化或建议不可用，请重新生成建议。'
        : assistantErrorText(c)
    }
  } finally {
    if (alive) busy.value = false
  }
}
async function pollJob(id: string) {
  if (
    !alive ||
    (job.value &&
      ['completed', 'failed', 'interrupted', 'needs_recovery'].includes(job.value.status))
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
      !['completed', 'failed', 'interrupted', 'needs_recovery'].includes(job.value.status))
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
watch(() => props.proposal.id, () => { selection.value = batchItems.value.map(x => x.media_id) })
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
        {{ kindLabels[proposal.kind] || '操作审批' }}
      </h3>
      <span class="rounded-full bg-surface-2 px-3 py-1 text-sm text-muted">{{
        job ? jobLabels[job.status] || status : status
      }}</span>
    </div>
    <p class="font-medium text-ink">
      {{ proposal.target_label }}
      <span v-if="proposal.target_id" class="text-sm text-muted">#{{ proposal.target_id }}</span>
    </p>
    <p v-if="proposal.reason" class="text-sm leading-relaxed text-muted">{{ proposal.reason }}</p>
    <div class="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted">
      <span>影响 {{ proposal.impact_count || 1 }} 个对象</span><span v-if="proposal.reversibility">{{ proposal.reversibility }}</span>
    </div>
    <details v-if="batchItems.length" class="rounded-xl border border-line p-3">
      <summary class="min-h-11 cursor-pointer text-sm text-ink focus-ring">选择要修改的媒体 · {{ selection.length }}/{{ batchItems.length }}</summary>
      <label v-for="item in batchItems" :key="item.media_id" class="flex min-h-11 cursor-pointer items-center gap-3 py-2 text-sm text-ink"><input v-model="selection" type="checkbox" :value="item.media_id" :disabled="busy || state !== 'pending' || expired || !enabled" class="h-5 w-5 accent-accent" /><span class="min-w-0 [overflow-wrap:anywhere]">{{ item.title || '媒体' }} #{{ item.media_id }}</span></label>
      <UiButton v-if="selectionDirty" class="mt-2 min-h-11" :disabled="!selection.length || busy || expired || !enabled" :loading="busy" @click="saveSelection">为选中的 {{ selection.length }} 项重新生成审批</UiButton>
    </details>
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
    <div v-if="(proposal.impact_count || 0) > 1 && proposal.kind !== 'media_batch_update'" class="space-y-2">
      <UiButton class="min-h-11" variant="ghost" :disabled="affectedBusy" @click="loadAffected()">查看完整影响清单</UiButton>
      <div v-if="affectedOpen" class="max-h-64 overflow-y-auto rounded-xl bg-surface-2 p-3 text-sm text-muted">
        <p v-for="item in affected" :key="String(item.type) + String(item.id)" class="mb-2 [overflow-wrap:anywhere]">{{ item.label }} #{{ item.id }}<span v-if="item.before"><br />{{ preview(item.before as Record<string, unknown>) }} → {{ preview(item.after as Record<string, unknown>) }}</span></p>
        <UiButton v-if="affectedMore" class="min-h-11" :disabled="affectedBusy" @click="loadAffected(true)">继续查看</UiButton>
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
        :disabled="!actionable || selectionDirty"
        :loading="busy"
        @click="act(true)"
        >{{ confirmLabel }}</UiButton
      ><UiButton
        data-reject
        class="min-h-11"
        :disabled="!actionable"
        @click="act(false)"
        >拒绝</UiButton
      >
    </div>
    <p v-if="job" role="status" class="text-sm text-muted">
      {{ jobLabels[job.status] || '任务状态待核实' }}<span v-if="job.progress != null"> · {{ job.progress }}%</span> · {{ job.job_id
      }}<br v-if="job.message" /><span v-if="job.message">{{
        job.message
      }}</span>
    </p>
    <p v-if="error" role="alert" class="text-sm text-danger">{{ error }}</p>
  </UiCard>
</template>
