<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import {
  MessageSquare,
  Plus,
  Send,
  Square,
  RefreshCw,
  Trash2,
  ChevronDown,
  Check,
  ShieldCheck,
  Loader2,
  History,
  X,
} from 'lucide-vue-next'
import { authIdentity, authState } from '../auth'
import { API_BASE_URL } from '../config'
import { PageHeader, UiButton, UiCard } from './ui'
import ChatMessages from './assistant/ChatMessages.vue'
import MediaResults from './assistant/MediaResults.vue'
import ProposalCard from './assistant/ProposalCard.vue'
import ApprovalPanel from './assistant/ApprovalPanel.vue'
import ProjectResultCard from './assistant/ProjectResultCard.vue'
import ModelSwitcher from './assistant/ModelSwitcher.vue'
import { useAssistantApprovals } from '../composables/useAssistantApprovals'
import { assistantErrorText, getAssistantModel, getCapabilities, updateAssistantModel } from '../utils/assistantApi'
import type {
  AssistantModelConfigDTO,
  AssistantModelUpdateRequest,
  CapabilitiesDTO,
  ProposalDTO,
  SessionDTO,
} from '../types/assistant'
import { AsyncMediaDetail as MediaDetail } from './asyncComponents'
import { useAssistantChat } from '../composables/useAssistantChat'
import { assistantPanelStore } from '../stores/assistantPanelStore'
import type { Media } from '../types'

const props = withDefaults(defineProps<{
  mode?: 'page' | 'sidebar'
}>(), {
  mode: 'page',
})

const emit = defineEmits<{
  close: []
}>()

const isSidebar = computed(() => props.mode === 'sidebar')

const chat = useAssistantChat()
const approvals = useAssistantApprovals()
const { items: approvalItems, pendingCount, tab: approvalTab, busy: approvalBusy, error: approvalError, hasMore: approvalMore } = approvals
const approvalOpen = ref(false), capabilities = ref<CapabilitiesDTO | null>(null)
const modelConfig = ref<AssistantModelConfigDTO | null>(null)
const modelBusy = ref(false)
const modelError = ref('')
let capabilityRequest = new AbortController()
let modelRequest = new AbortController()
async function loadCapabilities() {
  capabilityRequest.abort(); capabilityRequest = new AbortController(); const request = capabilityRequest
  if (!authIdentity() || !authState.user?.is_admin) return
  try {
    const value = await getCapabilities({ signal: request.signal })
    if (!request.signal.aborted && Array.isArray(value?.file_roots)) capabilities.value = value
  } catch { /* Capability unavailable is displayed explicitly. */ }
}
async function loadModelConfig() {
  modelRequest.abort(); modelRequest = new AbortController(); const request = modelRequest
  if (!authIdentity() || !authState.user?.is_admin) return
  try {
    const value = await getAssistantModel({ signal: request.signal })
    if (!request.signal.aborted && typeof value?.model === 'string') {
      modelConfig.value = value
      modelError.value = ''
    }
  } catch (e) {
    if (!request.signal.aborted) {
      modelError.value = assistantErrorText(e)
    }
  }
}
function ensureModelConfigLoaded() {
  if (!modelConfig.value && !modelBusy.value) {
    void loadModelConfig()
  }
}
async function applyModelUpdate(payload: AssistantModelUpdateRequest) {
  if (modelBusy.value || !authIdentity() || !authState.user?.is_admin) return
  modelBusy.value = true
  modelError.value = ''
  try {
    const updated = await updateAssistantModel(payload)
    if (alive && typeof updated?.model === 'string') {
      modelConfig.value = updated
    }
  } catch (e) {
    if (alive) modelError.value = assistantErrorText(e)
  } finally {
    if (alive) modelBusy.value = false
  }
}
const readableRoots = computed(() =>
  (capabilities.value?.file_roots || []).filter(x => x.readable).map(x => x.display_name).join('、'),
)
function approvalChanged() { void chat.refreshProposals(); void approvals.refresh() }
function jumpToProposal(proposal: ProposalDTO) {
  if (loading.value || sending.value) return
  approvalOpen.value = false
  const item = sessions.value.find(x => x.id === proposal.session_id) || { id: proposal.session_id, title: proposal.session_title || '历史对话', state: 'active' }
  chooseSession(item)
}

const {
  sessions,
  session,
  run,
  messages,
  results,
  proposals,
  availability,
  loading,
  sending,
  connected,
  error,
  toolStatus,
  truncated,
  olderOffset,
  moreSessions,
  moreProposals,
  allowed,
  active,
  canSend,
  hasRetry,
} = chat

watch(
  [() => active.value, () => pendingCount.value],
  ([isActive, pending]) => {
    if (!isSidebar.value) return
    assistantPanelStore.state.activeRun = isActive
    assistantPanelStore.state.pendingCount = pending
  },
  { immediate: true },
)
watch(
  () => availability.value.enabled,
  (enabled) => {
    if (enabled && !modelConfig.value) {
      void loadModelConfig()
    }
  },
)

const draft = ref(''),
  selectedMedia = ref<Media | null>(null),
  mediaError = ref(''),
  clearPrompt = ref(false)
const historyExpanded = ref(false)
const messagesBodyRef = ref<HTMLElement | null>(null)

function sessionDate(item: SessionDTO) {
  const value = item.updated_at || item.created_at
  if (!value) return null
  const date = new Date(/[zZ]|[+-]\d{2}:\d{2}$/.test(value) ? value : value + 'Z')
  return Number.isNaN(date.getTime()) ? null : date
}
function sessionDateLabel(item: SessionDTO) {
  const date = sessionDate(item)
  return date ? new Intl.DateTimeFormat('zh-CN', { month: 'short', day: 'numeric' }).format(date) : ''
}
const sessionGroups = computed(() => {
  const today = new Date()
  today.setHours(0, 0, 0, 0)
  const groups = [
    { label: '今天', items: [] as SessionDTO[] },
    { label: '昨天', items: [] as SessionDTO[] },
    { label: '最近 7 天', items: [] as SessionDTO[] },
    { label: '更早', items: [] as SessionDTO[] },
  ]
  const yesterday = new Date(today)
  yesterday.setDate(today.getDate() - 1)
  const week = new Date(today)
  week.setDate(today.getDate() - 6)
  const sorted = [...sessions.value].sort((a, b) =>
    (sessionDate(b)?.getTime() || 0) - (sessionDate(a)?.getTime() || 0),
  )
  for (const item of sorted) {
    const date = sessionDate(item)
    const index = !date ? 3 : date >= today ? 0 : date >= yesterday ? 1 : date >= week ? 2 : 3
    groups[index]!.items.push(item)
  }
  return groups.filter((group) => group.items.length)
})
function chooseSession(item: SessionDTO) {
  if (loading.value || sending.value) return
  historyExpanded.value = false
  clearPrompt.value = false
  void chat.selectSession(item)
}
function newConversation() {
  historyExpanded.value = false
  clearPrompt.value = false
  void chat.newSession()
}
const statusLabels: Record<string, string> = {
  running: '正在回复',
  submitting: '正在发送',
  submission_unknown: '正在核实提交',
  reconciling: '正在恢复任务',
  stopping: '正在停止，等待任务结束',
  completed: '回复完成',
  cancelled: '回复已停止',
  failed: '回复失败',
  interrupted: '回复中断，等待核实',
}
const status = computed(() =>
  run.value
    ? statusLabels[run.value.status] || '任务状态待核实'
    : availability.value.busy
      ? '媒体管家正在处理任务'
      : '可以开始对话',
)
let alive = true,
  focusFrame = 0
const input = ref<HTMLTextAreaElement | null>(null)
function keepComposerVisible() {
  cancelAnimationFrame(focusFrame)
  focusFrame = requestAnimationFrame(() => {
    focusFrame = requestAnimationFrame(() => {
      focusFrame = 0
      if (alive && document.activeElement === input.value)
        input.value?.closest('form')?.scrollIntoView({
          block: 'nearest',
          inline: 'nearest',
          behavior: 'auto',
        })
    })
  })
}
async function send() {
  if (!canSend.value) return
  await chat.send(draft.value)
  if (run.value && !hasRetry.value) draft.value = ''
  if (isSidebar.value) {
    await nextTick()
    if (messagesBodyRef.value) {
      messagesBodyRef.value.scrollTop = messagesBodyRef.value.scrollHeight
    }
  }
}
async function useSuggestion(text: string) {
  draft.value = text
  await nextTick()
  input.value?.focus()
}
function key(event: KeyboardEvent) {
  if (
    event.key === 'Enter' &&
    (event.ctrlKey || event.metaKey) &&
    !event.isComposing
  ) {
    event.preventDefault()
    void send()
  }
}
async function openMedia(id: number) {
  const token = authIdentity()
  mediaError.value = ''
  try {
    const response = await axios.get(API_BASE_URL + '/media/' + id)
    if (alive && authIdentity() === token) selectedMedia.value = response.data
  } catch {
    if (alive && authIdentity() === token)
      mediaError.value = '媒体暂不可用，请返回媒体库核实。'
  }
}
async function clear() {
  clearPrompt.value = false
  await chat.clear()
}
function focusComposer() {
  input.value?.focus()
}
defineExpose({
  focusComposer,
  hasSubOverlay: () => approvalOpen.value || Boolean(selectedMedia.value),
})

onMounted(() => {
  void chat.initialize()
  void loadCapabilities()
  void loadModelConfig()
  window.addEventListener('he-assistant-approval-changed', approvalChanged)
  window.visualViewport?.addEventListener('resize', keepComposerVisible)
  window.addEventListener('resize', keepComposerVisible)
})
watch(
  () => [authIdentity(), authState.user?.id, authState.user?.is_admin],
  () => {
    capabilityRequest.abort(); modelRequest.abort()
    capabilities.value = null; modelConfig.value = null; modelError.value = ''
    approvalOpen.value = false; void loadCapabilities(); void loadModelConfig()
    draft.value = ''
    selectedMedia.value = null
    clearPrompt.value = false
    if (allowed.value) void chat.initialize()
  },
)
onBeforeUnmount(() => {
  capabilityRequest.abort(); modelRequest.abort()
  window.removeEventListener('he-assistant-approval-changed', approvalChanged)
  alive = false
  cancelAnimationFrame(focusFrame)
  window.visualViewport?.removeEventListener('resize', keepComposerVisible)
  window.removeEventListener('resize', keepComposerVisible)
  if (isSidebar.value) {
    assistantPanelStore.state.activeRun = false
    assistantPanelStore.state.pendingCount = 0
  }
})
</script>

<template>
  <!-- Sidebar Mode -->
  <div v-if="isSidebar" class="he-assistant-sidebar flex h-full min-h-0 min-w-0 flex-col bg-sidebar/95">
    <header class="flex shrink-0 items-center justify-between gap-2 border-b border-line/80 bg-surface/92 px-4 py-3 backdrop-blur-xl">
      <div class="flex min-w-0 items-center gap-2.5">
        <span class="grid size-8 shrink-0 place-items-center rounded-xl border border-accent/25 bg-accent/12 text-accent shadow-[0_4px_14px_-4px_rgb(var(--color-accent)/0.45)]" aria-hidden="true">
          <MessageSquare :size="16" />
        </span>
        <div class="min-w-0">
          <div class="flex items-center gap-2">
            <h2 class="truncate text-body font-semibold tracking-tight text-ink">媒体库管家</h2>
            <span
              v-if="allowed"
              class="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2/80 px-2 py-0.5 text-[11px] font-medium text-muted"
            >
              <span
                class="size-1.5 rounded-full"
                :class="!availability.enabled ? 'bg-subtle/60' : active ? 'bg-accent animate-pulse' : 'bg-emerald-400'"
                aria-hidden="true"
              ></span>
              <span>{{ !availability.enabled ? '未启用' : active ? '回复中' : '在线' }}</span>
            </span>
          </div>
          <p class="truncate text-[11px] text-subtle">搜索、推荐与整理；变更由你确认</p>
        </div>
      </div>
      <div class="flex shrink-0 items-center gap-1">
        <button
          v-if="allowed"
          type="button"
          class="inline-flex h-8 items-center gap-1.5 rounded-lg border px-2 text-xs font-medium transition-colors duration-150 focus-ring"
          :class="historyExpanded
            ? 'border-accent/40 bg-accent/15 text-ink'
            : 'border-line bg-surface-2/75 text-muted hover:border-line-strong hover:bg-surface-3 hover:text-ink'"
          :aria-expanded="historyExpanded"
          aria-controls="assistant-sidebar-history"
          title="对话历史"
          @click="historyExpanded = !historyExpanded"
        >
          <History :size="14" aria-hidden="true" />
          <span v-if="sessions.length" class="tabular-nums">{{ sessions.length }}</span>
        </button>
        <button
          v-if="allowed"
          type="button"
          class="grid size-8 place-items-center rounded-lg border border-line bg-surface-2/75 text-muted transition-colors duration-150 hover:border-line-strong hover:bg-surface-3 hover:text-ink focus-ring disabled:opacity-50"
          :disabled="!availability.enabled || loading || sending"
          title="新对话"
          aria-label="新对话"
          @click="newConversation"
        >
          <Plus :size="15" aria-hidden="true" />
        </button>
        <button
          type="button"
          class="grid size-8 place-items-center rounded-lg text-subtle transition-colors duration-150 hover:bg-surface-2 hover:text-ink focus-ring"
          title="关闭媒体库管家"
          aria-label="关闭媒体库管家"
          @click="emit('close')"
        >
          <X :size="17" aria-hidden="true" />
        </button>
      </div>
    </header>

    <div v-if="!allowed" class="p-4">
      <div class="rounded-2xl border border-line bg-surface/60 p-5 text-sm text-muted">
        此功能仅向管理员开放。
      </div>
    </div>

    <template v-else>
      <div
        v-if="historyExpanded"
        id="assistant-sidebar-history"
        class="shrink-0 border-b border-line/80 bg-surface-2/55"
      >
        <div class="flex items-center justify-between gap-2 border-b border-line/60 px-4 py-2">
          <span class="text-xs font-semibold text-ink">历史对话</span>
          <UiButton size="sm" variant="primary" class="min-h-7 px-2.5 text-xs" :disabled="!availability.enabled || loading || sending" @click="newConversation">
            <template #icon><Plus :size="13" /></template>新对话
          </UiButton>
        </div>
        <nav class="custom-scrollbar max-h-[38vh] space-y-3 overflow-y-auto overscroll-contain p-2.5" aria-label="历史对话">
          <div v-if="!sessions.length" class="px-3 py-6 text-center text-xs leading-relaxed text-subtle">
            {{ loading ? '正在加载对话…' : '还没有对话，开始聊聊你的媒体库吧。' }}
          </div>
          <section v-for="group in sessionGroups" :key="group.label" :aria-label="group.label">
            <h3 class="px-2.5 pb-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">{{ group.label }}</h3>
            <div class="space-y-1">
              <button
                v-for="item in group.items"
                :key="item.id"
                type="button"
                :aria-current="session?.id === item.id ? 'page' : undefined"
                :disabled="loading || sending"
                :title="item.title"
                class="assistant-history-row group relative flex min-h-11 w-full items-center gap-2 rounded-xl border px-2.5 py-1.5 text-left transition-colors duration-150 focus-ring-inset disabled:cursor-wait disabled:opacity-60"
                :class="session?.id === item.id ? 'border-accent/30 bg-accent/12 text-ink shadow-[inset_0_1px_0_var(--he-border-specular)]' : 'border-transparent text-muted hover:bg-surface-2/80 hover:text-ink'"
                @click="chooseSession(item)"
              >
                <span v-if="session?.id === item.id" class="h-5 w-1 shrink-0 rounded-full bg-accent" aria-hidden="true"></span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-xs font-medium">{{ item.title }}</span>
                  <span class="mt-0.5 flex items-center gap-1.5 text-[11px] text-subtle">
                    <span v-if="item.state === 'deleting'" class="text-muted">正在清除</span>
                    <span v-else>{{ sessionDateLabel(item) || '媒体库管家' }}</span>
                  </span>
                </span>
                <Check v-if="session?.id === item.id" :size="13" class="shrink-0 text-accent" aria-hidden="true" />
              </button>
            </div>
          </section>
          <UiButton v-if="moreSessions" variant="ghost" size="sm" class="min-h-9 w-full" :disabled="loading || sending" @click="chat.loadMoreSessions">加载更多对话</UiButton>
        </nav>
      </div>

      <div class="flex shrink-0 flex-wrap items-center justify-between gap-2 border-b border-line/70 bg-surface/60 px-4 py-2">
        <div class="min-w-0 flex-1">
          <div class="flex min-w-0 items-center gap-2">
            <span class="size-1.5 shrink-0 rounded-full" :class="active ? 'bg-accent animate-pulse' : 'bg-accent/55'" aria-hidden="true"></span>
            <p class="truncate text-xs font-semibold text-ink">{{ session?.title || '开始一段新对话' }}</p>
          </div>
          <p role="status" aria-live="polite" class="mt-0.5 pl-3.5 text-[11px] text-muted">
            {{ loading ? '正在加载…' : status }}<span v-if="active && !connected"> · 未连接</span>
          </p>
        </div>
        <div class="flex shrink-0 flex-wrap items-center gap-1.5">
          <UiButton class="min-h-8 px-2.5 text-xs" size="sm" @click="approvalOpen = true; approvals.refresh()">
            <template #icon><ShieldCheck :size="14" /></template>待审批
            <span class="ml-0.5 inline-flex min-w-4 items-center justify-center rounded-full px-1 text-[11px] tabular-nums" :class="pendingCount > 0 ? 'bg-accent text-on-accent' : 'bg-accent/15 text-accent-glow'" aria-live="polite">{{ pendingCount }}</span>
          </UiButton>
          <UiButton v-if="run" class="min-h-8 px-2 text-xs" size="sm" variant="ghost" title="重新连接" @click="chat.reconnect">
            <template #icon><RefreshCw :size="13" /></template>
          </UiButton>
          <UiButton v-if="active" class="min-h-8 px-2 text-xs" size="sm" variant="danger" @click="chat.stop">
            <template #icon><Square :size="13" /></template>停止
          </UiButton>
          <UiButton v-if="session" class="min-h-8 px-2 text-xs" size="sm" variant="ghost" title="清除对话" aria-label="清除对话" @click="clearPrompt = true">
            <template #icon><Trash2 :size="13" /></template>
          </UiButton>
        </div>
      </div>

      <details class="assistant-cap-disclosure shrink-0 border-b border-line/70 bg-surface-2/35 px-4 text-xs text-muted">
        <summary class="flex min-h-9 cursor-pointer items-center justify-between gap-2 text-xs font-medium text-subtle hover:text-ink focus-ring">
          <span class="flex min-w-0 items-center gap-1.5">
            <ShieldCheck :size="13" class="shrink-0 text-accent" aria-hidden="true" />
            <span class="truncate">读取无需审批 · 日常修改按你的要求执行</span>
          </span>
          <ChevronDown :size="14" class="assistant-cap-chevron shrink-0 text-subtle" aria-hidden="true" />
        </summary>
        <div class="space-y-1.5 pb-2.5 pt-1 text-xs leading-relaxed text-muted">
          <template v-if="capabilities">
            <p>可连续查询媒体资料、作者、文件目录、任务、日志和存储状态。</p>
            <p>文件读取范围：{{ readableRoots || '暂无可读目录' }}</p>
            <p v-if="capabilities.action_tools?.length">你在聊天中明确要求后，资料、评分、收藏、已读状态、标签改名与扫描维护可直接执行，并保留执行记录。</p>
            <p>只要建议或预览时不会修改。文件改名 / 移动与标签合并仍需审批；不支持永久删除媒体、清库或覆盖文件。</p>
            <p v-if="!capabilities.image_analysis_supported">可查看媒体预览；当前模型未分析图片、音视频内容。</p>
          </template>
          <p v-else>能力信息暂不可用，请稍后重新连接。</p>
        </div>
      </details>

      <div ref="messagesBodyRef" class="custom-scrollbar min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-4 py-4">
        <UiCard v-if="clearPrompt" padding="sm" class="space-y-3 border-danger/30 bg-danger/5">
          <p class="text-xs leading-relaxed text-ink">
            清除这段对话会先停止回复，并作废待确认建议。已批准的任务和长期偏好会保留。
          </p>
          <div class="flex flex-wrap gap-2">
            <UiButton class="min-h-9" size="sm" variant="danger" @click="clear">确认清除</UiButton>
            <UiButton class="min-h-9" size="sm" variant="ghost" @click="clearPrompt = false">取消</UiButton>
          </div>
        </UiCard>

        <div v-if="olderOffset > 0" class="flex justify-center">
          <UiButton size="sm" variant="ghost" class="min-h-9 border border-line bg-surface-2/70" @click="chat.loadOlder">更早的消息</UiButton>
        </div>

        <ChatMessages :messages="messages" :disabled="!availability.enabled || sending" compact @suggest="useSuggestion" />

        <p v-if="toolStatus" role="status" class="inline-flex max-w-full items-center gap-2 rounded-full border border-accent/25 bg-accent/8 px-3 py-1.5 text-xs text-ink">
          <Loader2 v-if="active" :size="13" class="shrink-0 animate-spin text-accent motion-reduce:animate-none" aria-hidden="true" />
          <span class="min-w-0 truncate">{{ toolStatus }}</span>
        </p>

        <MediaResults :results="results" compact @open="openMedia" />
        <ProjectResultCard :results="results" />

        <p v-if="truncated" class="text-xs text-muted">
          本轮部分结果超出展示上限，请缩小查询范围。
        </p>

        <section v-if="proposals.length" aria-label="待审阅建议" class="space-y-3">
          <div class="flex items-center gap-2">
            <h3 class="text-sm font-semibold text-ink">整理建议</h3>
            <span class="rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium tabular-nums text-accent-glow">{{ proposals.length }}</span>
          </div>
          <ProposalCard v-for="proposal in proposals" :key="proposal.id" :proposal="proposal" :enabled="availability.enabled" />
          <UiButton v-if="moreProposals" variant="ghost" class="min-h-9" @click="chat.loadMoreProposals">更多建议</UiButton>
        </section>

        <p v-if="run" class="text-xs text-subtle [overflow-wrap:anywhere]">
          用量：<template v-if="run.usage"
            >输入 {{ run.usage.input_tokens ?? '不可用' }} · 输出
            {{ run.usage.output_tokens ?? '不可用' }} · 合计
            {{ run.usage.total_tokens ?? '不可用' }} token</template
          ><template v-else>本轮不可用</template>
        </p>

        <div
          v-if="error || mediaError"
          role="alert"
          class="rounded-xl border border-danger/30 bg-danger/8 p-3 text-xs text-danger [overflow-wrap:anywhere]"
        >
          {{ error || mediaError }}
          <UiButton v-if="hasRetry" class="mt-2.5 min-h-9" size="sm" :disabled="sending" @click="chat.retrySend">重试原消息</UiButton>
        </div>
      </div>

      <form
        class="assistant-composer shrink-0 border-t border-line/80 bg-surface/94 p-3 backdrop-blur-xl transition-colors duration-150 focus-within:border-accent/45 motion-reduce:transition-none"
        @submit.prevent="send"
      >
        <div class="rounded-2xl border border-line bg-surface-2/85 p-2 transition-[border-color,box-shadow] duration-150 focus-within:border-accent/55 focus-within:ring-2 focus-within:ring-accent/20 motion-reduce:transition-none">
          <label for="assistant-sidebar-input" class="sr-only">发送消息</label>
          <textarea
            ref="input"
            id="assistant-sidebar-input"
            v-model="draft"
            rows="2"
            maxlength="8000"
            :disabled="!availability.enabled || sending || session?.state === 'deleting'"
            aria-describedby="assistant-sidebar-input-hint"
            class="block max-h-[28vh] min-h-[3.25rem] w-full min-w-0 resize-y rounded-xl bg-transparent px-2.5 py-1.5 text-sm leading-relaxed text-ink outline-none placeholder:text-subtle"
            placeholder="告诉管家你想找什么，例如：找一些温馨、还没看过的短篇漫画"
            @focus="keepComposerVisible"
            @keydown="key"
          />
          <div class="flex flex-wrap items-center justify-between gap-2 border-t border-line/60 px-1.5 pt-2">
            <div class="flex min-w-0 items-center gap-2">
              <ModelSwitcher
                compact
                :model-config="modelConfig"
                :busy="modelBusy"
                :disabled="active || sending"
                :error="modelError"
                @open="ensureModelConfigLoaded"
                @select-preset="applyModelUpdate({ preset_id: $event })"
                @delete-preset="applyModelUpdate({ delete_preset_id: $event })"
                @save-custom="applyModelUpdate($event)"
                @toggle-thinking="applyModelUpdate({ thinking_disabled: $event })"
              />
              <p id="assistant-sidebar-input-hint" class="hidden min-[400px]:block text-[11px] text-subtle tabular-nums">
                {{ draft.length }}/8000 · Ctrl/⌘+Enter
              </p>
            </div>
            <UiButton
              class="min-h-8"
              size="sm"
              type="submit"
              variant="primary"
              :loading="sending"
              :disabled="!canSend || !draft.trim()"
            >
              <template #icon><Send :size="14" /></template>发送
            </UiButton>
          </div>
        </div>
      </form>
    </template>

    <ApprovalPanel v-if="allowed" v-model:open="approvalOpen" :items="approvalItems" :pending-count="pendingCount" :tab="approvalTab" :busy="approvalBusy" :error="approvalError" :has-more="approvalMore" :enabled="availability.enabled" @tab="approvalTab = $event" @refresh="approvals.refresh()" @more="approvals.loadMore()" @jump="jumpToProposal" />
    <MediaDetail
      v-if="allowed && selectedMedia"
      :initial-media="selectedMedia"
      :all-media="[selectedMedia]"
      @close="selectedMedia = null"
      @updated="selectedMedia = $event"
      @navigate="selectedMedia = $event"
    />
  </div>

  <!-- Full-page Mode -->
  <div v-else class="he-assistant-page min-w-0 min-h-full">
    <PageHeader title="媒体库管家" description="搜索、推荐与整理；变更由你确认">
      <template #leading>
        <span class="grid size-10 shrink-0 place-items-center rounded-2xl border border-accent/25 bg-accent/12 text-accent shadow-[0_6px_20px_-6px_rgb(var(--color-accent)/0.45)]" aria-hidden="true">
          <MessageSquare :size="20" />
        </span>
      </template>
      <template v-if="allowed" #actions>
        <span class="inline-flex items-center gap-2 rounded-full border border-line bg-surface/80 px-3 py-1.5 text-xs font-medium text-muted">
          <span
            class="size-2 rounded-full"
            :class="!availability.enabled ? 'bg-subtle/60' : active ? 'bg-accent animate-pulse' : 'bg-emerald-400'"
            aria-hidden="true"
          ></span>
          <span>{{ !availability.enabled ? '服务未启用' : active ? '正在执行回复' : '管家在线' }}</span>
        </span>
      </template>
    </PageHeader>
    <div class="page-gutter pb-8">
      <div v-if="!allowed" class="page-container rounded-2xl border border-line bg-surface/60 p-6 text-muted">
        此功能仅向管理员开放。
      </div>
      <div v-else class="page-container min-w-0">
        <div
          class="mx-auto grid max-w-[1440px] min-w-0 gap-4 lg:grid-cols-[276px_minmax(0,1fr)] lg:gap-6 xl:grid-cols-[296px_minmax(0,1fr)]"
        >
          <aside class="assistant-history min-w-0 self-start rounded-2xl border border-line bg-surface/80 shadow-[var(--he-shadow-card)]" aria-label="对话历史">
            <div class="space-y-3 border-b border-line/70 p-3.5">
              <div class="hidden items-center justify-between gap-2 px-1 lg:flex">
                <div class="flex items-center gap-2">
                  <MessageSquare :size="16" class="text-accent" aria-hidden="true" />
                  <h2 class="text-sm font-semibold text-ink">对话历史</h2>
                </div>
                <span v-if="sessions.length" class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium tabular-nums text-subtle">{{ sessions.length }}</span>
              </div>
              <button
                type="button"
                class="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl px-1.5 text-left hover:bg-surface-2/60 focus-ring lg:hidden"
                :aria-expanded="historyExpanded"
                aria-controls="assistant-history-list"
                @click="historyExpanded = !historyExpanded"
              >
                <span class="flex min-w-0 items-center gap-2.5">
                  <MessageSquare :size="18" class="shrink-0 text-accent" aria-hidden="true" />
                  <span class="min-w-0">
                    <span class="block text-[11px] text-subtle">对话历史 · {{ sessions.length }}</span>
                    <span class="block truncate text-sm font-medium text-ink">{{ session?.title || '开始新对话' }}</span>
                  </span>
                </span>
                <ChevronDown :size="17" class="shrink-0 text-muted transition-transform duration-200 motion-reduce:transition-none" :class="{ 'rotate-180': historyExpanded }" aria-hidden="true" />
              </button>
              <UiButton class="min-h-10 w-full" size="sm" variant="primary" :disabled="!availability.enabled || loading || sending" @click="newConversation">
                <template #icon><Plus :size="16" /></template>新对话
              </UiButton>
            </div>
            <div id="assistant-history-list" :class="historyExpanded ? 'block' : 'hidden lg:block'">
              <nav class="assistant-history-list custom-scrollbar space-y-4 overflow-y-auto overscroll-contain p-2.5" aria-label="历史对话">
                <div v-if="!sessions.length" class="px-3 py-8 text-center text-sm leading-relaxed text-subtle">
                  {{ loading ? '正在加载对话…' : '还没有对话，开始聊聊你的媒体库吧。' }}
                </div>
                <section v-for="group in sessionGroups" :key="group.label" :aria-label="group.label">
                  <h3 class="px-3 pb-1.5 pt-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">{{ group.label }}</h3>
                  <div class="space-y-1">
                    <button
                      v-for="item in group.items"
                      :key="item.id"
                      type="button"
                      :aria-current="session?.id === item.id ? 'page' : undefined"
                      :disabled="loading || sending"
                      :title="item.title"
                      class="assistant-history-row group relative flex min-h-13 w-full items-center gap-2.5 rounded-xl border px-3 py-2 text-left transition-colors duration-150 focus-ring-inset disabled:cursor-wait disabled:opacity-60 motion-reduce:transition-none"
                      :class="session?.id === item.id ? 'border-accent/30 bg-accent/12 text-ink shadow-[inset_0_1px_0_var(--he-border-specular)]' : 'border-transparent text-muted hover:bg-surface-2/80 hover:text-ink'"
                      @click="chooseSession(item)"
                    >
                      <span
                        v-if="session?.id === item.id"
                        class="h-6 w-1 shrink-0 rounded-full bg-accent"
                        aria-hidden="true"
                      ></span>
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-sm font-medium">{{ item.title }}</span>
                        <span class="mt-0.5 flex items-center gap-2 text-[11px] text-subtle">
                          <span v-if="item.state === 'deleting'" class="text-muted">正在清除</span>
                          <span v-else>{{ sessionDateLabel(item) || '媒体库管家' }}</span>
                          <span v-if="session?.id === item.id" class="font-medium text-accent-glow">当前对话</span>
                        </span>
                      </span>
                      <Check v-if="session?.id === item.id" :size="14" class="shrink-0 text-accent" aria-hidden="true" />
                    </button>
                  </div>
                </section>
                <UiButton v-if="moreSessions" variant="ghost" size="sm" class="min-h-10 w-full" :disabled="loading || sending" @click="chat.loadMoreSessions">加载更多对话</UiButton>
              </nav>
            </div>
            <div class="mt-auto hidden border-t border-line/70 px-4 py-3 lg:block">
              <p v-if="!availability.enabled" class="mb-2 text-xs leading-relaxed text-muted">管家暂未启用，历史和停止操作仍可使用。</p>
              <div class="flex items-start gap-2 text-xs leading-relaxed text-subtle">
                <ShieldCheck :size="15" class="mt-0.5 shrink-0 text-muted" aria-hidden="true" />
                <p>可读取 HE 项目；明确要求的日常修改可直接执行。账号凭据默认隐藏。</p>
              </div>
            </div>
          </aside>

          <section class="assistant-stage flex min-w-0 flex-col rounded-2xl border border-line bg-surface/65 shadow-[var(--he-shadow-card)]" aria-label="对话工作区">
            <header class="assistant-stage-header flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-t-2xl border-b border-line/80 bg-surface/92 px-4 py-3 backdrop-blur-xl sm:px-5">
              <div class="min-w-0 flex-1 basis-full sm:basis-auto">
                <div class="flex min-w-0 items-center gap-2.5">
                  <span
                    class="size-2 shrink-0 rounded-full"
                    :class="active ? 'bg-accent animate-pulse' : 'bg-accent/55'"
                    aria-hidden="true"
                  ></span>
                  <h2 class="line-clamp-1 text-base font-semibold text-ink sm:text-[1.05rem]">{{ session?.title || '开始一段新对话' }}</h2>
                </div>
                <p role="status" aria-live="polite" class="mt-0.5 pl-4.5 text-xs text-muted sm:text-sm">
                  {{ loading ? '正在加载…' : status }}<span v-if="active && !connected"> · 未连接</span>
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <UiButton class="min-h-9" size="sm" @click="approvalOpen = true; approvals.refresh()">
                  <template #icon><ShieldCheck :size="15" /></template>待审批
                  <span class="ml-1 inline-flex min-w-5 items-center justify-center rounded-full px-1.5 text-xs tabular-nums" :class="pendingCount > 0 ? 'bg-accent text-on-accent' : 'bg-accent/15 text-accent-glow'" aria-live="polite">{{ pendingCount }}</span>
                </UiButton>
                <UiButton
                  v-if="run"
                  class="min-h-9"
                  size="sm"
                  variant="ghost"
                  @click="chat.reconnect"
                  ><template #icon><RefreshCw :size="14" /></template
                  >重新连接</UiButton
                ><UiButton
                  v-if="active"
                  class="min-h-9"
                  size="sm"
                  variant="danger"
                  @click="chat.stop"
                  ><template #icon><Square :size="14" /></template
                  >停止回复</UiButton
                ><UiButton
                  v-if="session"
                  class="min-h-9"
                  size="sm"
                  variant="ghost"
                  @click="clearPrompt = true"
                  ><template #icon><Trash2 :size="14" /></template
                  >清除对话</UiButton
                >
              </div>
            </header>

            <details class="assistant-cap-disclosure border-b border-line/70 bg-surface-2/40 px-4 text-sm text-muted sm:px-5">
              <summary class="flex min-h-10 cursor-pointer items-center justify-between gap-2 text-xs font-medium text-subtle hover:text-ink focus-ring sm:text-sm">
                <span class="flex min-w-0 items-center gap-2">
                  <ShieldCheck :size="14" class="shrink-0 text-accent" aria-hidden="true" />
                  <span class="truncate">读取无需审批 · 日常修改按你的要求执行</span>
                </span>
                <ChevronDown :size="15" class="assistant-cap-chevron shrink-0 text-subtle" aria-hidden="true" />
              </summary>
              <div class="space-y-1.5 pb-3 pt-1 text-xs leading-relaxed text-muted sm:text-sm">
                <template v-if="capabilities">
                  <p>可连续查询媒体资料、作者、文件目录、任务、日志和存储状态。</p>
                  <p>文件读取范围：{{ readableRoots || '暂无可读目录' }}</p>
                  <p v-if="capabilities.action_tools?.length">你在聊天中明确要求后，资料、评分、收藏、已读状态、标签改名与扫描维护可直接执行，并保留执行记录。</p>
                  <p>只要建议或预览时不会修改。文件改名 / 移动与标签合并仍需审批；不支持永久删除媒体、清库或覆盖文件。</p>
                  <p v-if="!capabilities.image_analysis_supported">可查看媒体预览；当前模型未分析图片、音视频内容。</p>
                </template>
                <p v-else>能力信息暂不可用，请稍后重新连接。</p>
              </div>
            </details>

            <div class="min-w-0 flex-1 space-y-5 px-4 py-5 sm:px-6">
              <UiCard v-if="clearPrompt" padding="sm" class="space-y-3 border-danger/30 bg-danger/5">
                <p class="text-sm leading-relaxed text-ink">
                  清除这段对话会先停止回复，并作废待确认建议。已批准的任务和长期偏好会保留。
                </p>
                <div class="flex flex-wrap gap-2.5">
                  <UiButton class="min-h-10" size="sm" variant="danger" @click="clear">确认清除</UiButton>
                  <UiButton
                    class="min-h-10"
                    size="sm"
                    variant="ghost"
                    @click="clearPrompt = false"
                    >取消</UiButton
                  >
                </div>
              </UiCard>

              <div v-if="olderOffset > 0" class="flex justify-center">
                <UiButton
                  size="sm"
                  variant="ghost"
                  class="min-h-10 border border-line bg-surface-2/70"
                  @click="chat.loadOlder"
                  >更早的消息</UiButton
                >
              </div>

              <ChatMessages :messages="messages" :disabled="!availability.enabled || sending" @suggest="useSuggestion" />

              <p v-if="toolStatus" role="status" class="inline-flex max-w-full items-center gap-2 rounded-full border border-accent/25 bg-accent/8 px-3.5 py-1.5 text-sm text-ink">
                <Loader2 v-if="active" :size="14" class="shrink-0 animate-spin text-accent motion-reduce:animate-none" aria-hidden="true" />
                <span class="min-w-0 truncate">{{ toolStatus }}</span>
              </p>

              <MediaResults :results="results" @open="openMedia" />
              <ProjectResultCard :results="results" />

              <p v-if="truncated" class="text-xs text-muted">
                本轮部分结果超出展示上限，请缩小查询范围。
              </p>

              <section
                v-if="proposals.length"
                aria-label="待审阅建议"
                class="space-y-3"
              >
                <div class="flex items-center gap-2">
                  <h2 class="text-sm font-semibold text-ink sm:text-base">整理建议</h2>
                  <span class="rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium tabular-nums text-accent-glow">{{ proposals.length }}</span>
                </div>
                <ProposalCard
                  v-for="proposal in proposals"
                  :key="proposal.id"
                  :proposal="proposal"
                  :enabled="availability.enabled"
                />
                <UiButton
                  v-if="moreProposals"
                  variant="ghost"
                  class="min-h-10"
                  @click="chat.loadMoreProposals"
                  >更多建议</UiButton
                >
              </section>

              <p v-if="run" class="text-xs text-subtle [overflow-wrap:anywhere]">
                用量：<template v-if="run.usage"
                  >输入 {{ run.usage.input_tokens ?? '不可用' }} · 输出
                  {{ run.usage.output_tokens ?? '不可用' }} · 合计
                  {{ run.usage.total_tokens ?? '不可用' }} token</template
                ><template v-else>本轮不可用</template>
              </p>

              <div
                v-if="error || mediaError"
                role="alert"
                class="rounded-xl border border-danger/30 bg-danger/8 p-3.5 text-sm text-danger [overflow-wrap:anywhere]"
              >
                {{ error || mediaError }}
                <UiButton
                  v-if="hasRetry"
                  class="mt-3 min-h-10"
                  size="sm"
                  :disabled="sending"
                  @click="chat.retrySend"
                  >重试原消息</UiButton
                >
              </div>
            </div>

            <form
              class="assistant-composer mt-auto min-w-0 rounded-b-2xl border-t border-line/80 bg-surface/94 p-3 backdrop-blur-xl transition-colors duration-150 focus-within:border-accent/45 sm:px-5 sm:py-3.5 motion-reduce:transition-none"
              @submit.prevent="send"
            >
              <div class="rounded-2xl border border-line bg-surface-2/85 p-2 transition-[border-color,box-shadow] duration-150 focus-within:border-accent/55 focus-within:ring-2 focus-within:ring-accent/20 motion-reduce:transition-none">
                <label for="assistant-input" class="sr-only">发送消息</label>
                <textarea
                  ref="input"
                  id="assistant-input"
                  v-model="draft"
                  rows="2"
                  maxlength="8000"
                  :disabled="
                    !availability.enabled ||
                    sending ||
                    session?.state === 'deleting'
                  "
                  aria-describedby="assistant-input-hint"
                  class="block max-h-[36vh] min-h-[3.75rem] w-full min-w-0 resize-y rounded-xl bg-transparent px-3 py-2 text-base leading-relaxed text-ink outline-none placeholder:text-subtle"
                  placeholder="告诉管家你想找什么，例如：找一些温馨、还没看过的短篇漫画"
                  @focus="keepComposerVisible"
                  @keydown="key"
                />
                <div
                  class="flex flex-wrap items-center justify-between gap-3 border-t border-line/60 px-2 pt-2"
                >
                  <div class="flex min-w-0 flex-wrap items-center gap-2.5">
                    <ModelSwitcher
                      :model-config="modelConfig"
                      :busy="modelBusy"
                      :disabled="active || sending"
                      :error="modelError"
                      @open="ensureModelConfigLoaded"
                      @select-preset="applyModelUpdate({ preset_id: $event })"
                      @delete-preset="applyModelUpdate({ delete_preset_id: $event })"
                      @save-custom="applyModelUpdate($event)"
                      @toggle-thinking="applyModelUpdate({ thinking_disabled: $event })"
                    />
                    <p id="assistant-input-hint" class="text-xs text-subtle tabular-nums">
                      {{ draft.length }}/8000 · Ctrl/⌘ + Enter 发送
                    </p>
                  </div>
                  <UiButton
                    class="min-h-10"
                    size="sm"
                    type="submit"
                    variant="primary"
                    :loading="sending"
                    :disabled="!canSend || !draft.trim()"
                    ><template #icon><Send :size="15" /></template>发送</UiButton
                  >
                </div>
              </div>
            </form>
          </section>
        </div>
      </div>
    </div>
    <ApprovalPanel v-if="allowed" v-model:open="approvalOpen" :items="approvalItems" :pending-count="pendingCount" :tab="approvalTab" :busy="approvalBusy" :error="approvalError" :has-more="approvalMore" :enabled="availability.enabled" @tab="approvalTab = $event" @refresh="approvals.refresh()" @more="approvals.loadMore()" @jump="jumpToProposal" />
    <MediaDetail
      v-if="allowed && selectedMedia"
      :initial-media="selectedMedia"
      :all-media="[selectedMedia]"
      @close="selectedMedia = null"
      @updated="selectedMedia = $event"
      @navigate="selectedMedia = $event"
    />
  </div>
</template>

<style scoped>
.he-assistant-page {
  overflow-wrap: anywhere;
}
.he-assistant-sidebar {
  overflow-wrap: anywhere;
}
.assistant-history-list {
  max-height: 320px;
}
.assistant-cap-disclosure::details-content {
  block-size: 0;
  overflow: hidden;
  transition: block-size 220ms var(--ease-snappy), content-visibility 220ms allow-discrete;
}
.assistant-cap-disclosure[open]::details-content {
  block-size: auto;
}
.assistant-cap-chevron {
  transition: transform 200ms var(--ease-snappy);
}
.assistant-cap-disclosure[open] .assistant-cap-chevron {
  transform: rotate(180deg);
}
@media (min-width: 1024px) {
  .assistant-history {
    position: sticky;
    top: 1.25rem;
    display: flex;
    flex-direction: column;
    max-height: calc(100dvh - 2.5rem);
    min-height: min(620px, calc(100dvh - 180px));
  }
  .assistant-history-list {
    max-height: max(240px, calc(100dvh - 340px));
  }
  .assistant-stage-header {
    position: sticky;
    top: 0;
    z-index: 20;
  }
  .assistant-stage .assistant-composer {
    position: sticky;
    bottom: 0;
    z-index: 20;
  }
  :global(.he-app-shell:has(.he-assistant-page) .he-back-top) {
    bottom: 10.25rem;
  }
}
.assistant-composer {
  scroll-margin-block: 1rem;
  padding-bottom: max(0.875rem, env(safe-area-inset-bottom));
}
@media (prefers-reduced-motion: reduce) {
  .assistant-cap-disclosure::details-content,
  .assistant-cap-chevron {
    transition: none;
  }
}
:global(.he-app-shell:has(.he-assistant-page textarea:focus) .he-back-top) {
  display: none;
}
</style>
