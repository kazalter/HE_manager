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
  Sparkles,
  FolderOpen,
} from 'lucide-vue-next'
import { authState } from '../auth'
import { API_BASE_URL } from '../config'
import { PageHeader, UiButton, UiCard } from '../components/ui'
import ChatMessages from '../components/assistant/ChatMessages.vue'
import MediaResults from '../components/assistant/MediaResults.vue'
import ProposalCard from '../components/assistant/ProposalCard.vue'
import ApprovalPanel from '../components/assistant/ApprovalPanel.vue'
import ProjectResultCard from '../components/assistant/ProjectResultCard.vue'
import { useAssistantApprovals } from '../composables/useAssistantApprovals'
import { getCapabilities } from '../utils/assistantApi'
import type { ProposalDTO, CapabilitiesDTO } from '../types/assistant'
import { AsyncMediaDetail as MediaDetail } from '../components/asyncComponents'
import { useAssistantChat } from '../composables/useAssistantChat'
import type { Media } from '../types'
import type { SessionDTO } from '../types/assistant'

const chat = useAssistantChat()
const approvals = useAssistantApprovals()
const { items: approvalItems, pendingCount, tab: approvalTab, busy: approvalBusy, error: approvalError, hasMore: approvalHasMore, loadMore: loadMoreApprovals } = approvals
const approvalOpen = ref(false), capabilities = ref<CapabilitiesDTO | null>(null)
let capabilityRequest = new AbortController()
async function loadCapabilities() {
  capabilityRequest.abort(); capabilityRequest = new AbortController(); const request = capabilityRequest
  if (!authState.token || !authState.user?.is_admin) return
  try {
    const value = await getCapabilities({ signal: request.signal })
    if (!request.signal.aborted && Array.isArray(value?.file_roots)) capabilities.value = value
  } catch { /* Capability unavailable is displayed explicitly. */ }
}
const readableRoots = computed(() =>
  (capabilities.value?.file_roots || []).filter(x => x.readable).map(x => x.display_name).join(', '),
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

const draft = ref(''),
  selectedMedia = ref<Media | null>(null),
  mediaError = ref(''),
  clearPrompt = ref(false)
const historyExpanded = ref(false)
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
  const token = authState.token
  mediaError.value = ''
  try {
    const response = await axios.get(API_BASE_URL + '/media/' + id)
    if (alive && authState.token === token) selectedMedia.value = response.data
  } catch {
    if (alive && authState.token === token)
      mediaError.value = '媒体暂不可用，请返回媒体库核实。'
  }
}
async function clear() {
  clearPrompt.value = false
  await chat.clear()
}
onMounted(() => {
  void chat.initialize()
  void loadCapabilities()
  window.addEventListener('he-assistant-approval-changed', approvalChanged)
  window.visualViewport?.addEventListener('resize', keepComposerVisible)
  window.addEventListener('resize', keepComposerVisible)
})
watch(
  () => [authState.token, authState.user?.id, authState.user?.is_admin],
  () => {
    capabilityRequest.abort(); capabilities.value = null; approvalOpen.value = false; void loadCapabilities()
    draft.value = ''
    selectedMedia.value = null
    clearPrompt.value = false
    if (allowed.value) void chat.initialize()
  },
)
onBeforeUnmount(() => {
  capabilityRequest.abort(); window.removeEventListener('he-assistant-approval-changed', approvalChanged)
  alive = false
  cancelAnimationFrame(focusFrame)
  window.visualViewport?.removeEventListener('resize', keepComposerVisible)
  window.removeEventListener('resize', keepComposerVisible)
})
</script>

<template>
  <div class="he-assistant-page min-w-0 min-h-full">
    <PageHeader title="媒体库管家" description="搜索、推荐与整理；变更由你确认">
      <template #leading>
        <div class="grid size-10 place-items-center rounded-2xl bg-accent/12 text-accent ring-1 ring-accent/20">
          <MessageSquare :size="20" aria-hidden="true" />
        </div>
      </template>
    </PageHeader>
    <div class="page-gutter pb-10">
      <div v-if="!allowed" class="page-container text-muted">
        此功能仅向管理员开放。
      </div>
      <div v-else class="page-container min-w-0">
        <div
          class="mx-auto grid max-w-[1280px] min-w-0 gap-5 lg:grid-cols-[276px_minmax(0,1fr)] lg:gap-7"
        >
          <aside
            class="assistant-history min-w-0 self-start rounded-2xl border border-line/80 bg-surface/85 shadow-2xs backdrop-blur-md"
            aria-label="对话历史"
          >
            <div class="space-y-3 border-b border-line/60 p-3.5">
              <div class="hidden items-center justify-between gap-2 px-1 lg:flex">
                <div class="flex items-center gap-2">
                  <MessageSquare :size="16" class="text-accent" aria-hidden="true" />
                  <h2 class="text-sm font-semibold text-ink">对话历史</h2>
                </div>
                <span
                  v-if="sessions.length"
                  class="rounded-full bg-surface-2 px-2 py-0.5 text-[11px] font-medium tabular-nums text-subtle"
                >
                  {{ sessions.length }}
                </span>
              </div>
              <button
                type="button"
                class="flex min-h-11 w-full items-center justify-between gap-3 rounded-xl px-1.5 text-left focus-ring lg:hidden"
                :aria-expanded="historyExpanded"
                aria-controls="assistant-history-list"
                @click="historyExpanded = !historyExpanded"
              >
                <span class="flex min-w-0 items-center gap-2.5">
                  <MessageSquare :size="18" class="shrink-0 text-accent" aria-hidden="true" />
                  <span class="min-w-0">
                    <span class="block text-xs text-muted">对话历史</span>
                    <span class="block truncate text-sm font-medium text-ink">{{ session?.title || '开始新对话' }}</span>
                  </span>
                </span>
                <ChevronDown
                  :size="17"
                  class="shrink-0 text-muted transition-transform motion-reduce:transition-none"
                  :class="historyExpanded ? 'rotate-180' : ''"
                />
              </button>
              <UiButton
                class="min-h-11 w-full shadow-2xs"
                :disabled="!availability.enabled || loading || sending"
                @click="newConversation"
              >
                <template #icon><Plus :size="17" /></template>新对话
              </UiButton>
            </div>
            <div id="assistant-history-list" :class="historyExpanded ? 'block' : 'hidden lg:block'">
              <nav
                class="assistant-history-list custom-scrollbar space-y-4 overflow-y-auto overscroll-contain p-3.5 max-lh:max-h-[320px] lg:max-h-[calc(100vh-260px)]"
                aria-label="对话历史列表"
              >
                <div v-if="!sessions.length" class="rounded-xl border border-dashed border-line/70 px-3 py-8 text-center text-sm leading-relaxed text-muted">
                  {{ loading ? '正在加载对话...' : '还没有对话，开始聊聊你的媒体库吧。' }}
                </div>
                <section v-for="group in sessionGroups" :key="group.label" :aria-label="group.label">
                  <h3 class="px-2.5 pb-1.5 pt-1 text-[11px] font-semibold uppercase tracking-wider text-subtle">
                    {{ group.label }}
                  </h3>
                  <div class="space-y-1">
                    <button
                      v-for="item in group.items"
                      :key="item.id"
                      type="button"
                      :aria-current="session?.id === item.id ? 'page' : undefined"
                      :disabled="loading || sending"
                      :title="item.title"
                      class="assistant-history-row group relative flex min-h-14 w-full items-center gap-2.5 overflow-hidden rounded-xl border px-3 py-2 text-left transition-all duration-150 focus-ring disabled:opacity-50"
                      :class="
                        session?.id === item.id
                          ? 'border-accent/30 bg-accent/12 text-ink shadow-2xs before:absolute before:inset-y-2.5 before:left-0 before:w-1 before:rounded-r-full before:bg-accent'
                          : 'border-transparent text-muted hover:border-line/60 hover:bg-surface-hover hover:text-ink'
                      "
                      @click="chooseSession(item)"
                    >
                      <span class="min-w-0 flex-1">
                        <span class="block truncate text-sm font-medium">{{ item.title }}</span>
                        <span class="mt-1 flex items-center gap-2 text-xs text-subtle">
                          <span v-if="item.state === 'deleting'" class="text-muted">正在清除</span>
                          <span v-else>{{ sessionDateLabel(item) || '媒体库管家' }}</span>
                          <span v-if="session?.id === item.id" class="font-medium text-accent-glow">当前对话</span>
                        </span>
                      </span>
                      <Check v-if="session?.id === item.id" :size="15" class="shrink-0 text-accent" aria-hidden="true" />
                    </button>
                  </div>
                </section>
                <UiButton
                  v-if="moreSessions"
                  variant="ghost"
                  class="min-h-11 w-full"
                  :disabled="loading || sending"
                  @click="chat.loadMoreSessions"
                >
                  更早的对话
                </UiButton>
              </nav>
            </div>
            <div class="mt-auto rounded-b-2xl border-t border-line/70 bg-surface-2/40 px-4 py-3.5">
              <p v-if="!availability.enabled" class="mb-2 text-xs leading-relaxed text-muted">
                管家暂未启用，历史和停止功能仍可使用。
              </p>
              <div class="flex items-start gap-2 text-xs leading-relaxed text-subtle">
                <ShieldCheck :size="15" class="mt-0.5 shrink-0 text-accent/80" aria-hidden="true" />
                <p>可读取 HE 项目；修改需你批准。账号凭据默认隐藏。</p>
              </div>
            </div>
          </aside>

          <div class="min-w-0 space-y-5">
            <!-- 会话状态与快捷操作顶栏 -->
            <div
              class="flex min-w-0 flex-wrap items-center justify-between gap-3 rounded-2xl border border-line/80 bg-surface/85 px-4 py-3.5 shadow-2xs backdrop-blur-md sm:px-5"
            >
              <div class="min-w-0 flex-1 basis-full sm:basis-auto">
                <div class="flex items-center gap-2">
                  <Sparkles :size="16" class="shrink-0 text-accent" aria-hidden="true" />
                  <h2 class="line-clamp-1 text-base font-semibold text-ink sm:text-lg">
                    {{ session?.title || '开始新对话' }}
                  </h2>
                </div>
                <p role="status" aria-live="polite" class="mt-1 flex items-center gap-2 text-xs text-muted sm:text-sm">
                  <span
                    class="inline-block size-2 shrink-0 rounded-full"
                    :class="
                      active
                        ? 'animate-pulse bg-accent'
                        : !availability.enabled
                          ? 'bg-muted'
                          : 'bg-emerald-500/80'
                    "
                    aria-hidden="true"
                  />
                  <span>{{ loading ? '正在加载...' : status }}<span v-if="active && !connected"> · 未连接</span></span>
                </p>
              </div>
              <div class="flex flex-wrap items-center gap-2">
                <UiButton
                  class="min-h-11"
                  size="sm"
                  :variant="pendingCount > 0 ? 'primary' : 'secondary'"
                  @click="approvalOpen = true; approvals.refresh()"
                >
                  <template #icon><ShieldCheck :size="16" /></template>待你确认 ({{ pendingCount }})
                </UiButton>
                <UiButton
                  v-if="run"
                  class="min-h-11"
                  size="sm"
                  variant="ghost"
                  @click="chat.reconnect"
                >
                  <template #icon><RefreshCw :size="15" /></template>重新连接
                </UiButton>
                <UiButton
                  v-if="active"
                  class="min-h-11"
                  size="sm"
                  variant="danger"
                  @click="chat.stop"
                >
                  <template #icon><Square :size="15" /></template>停止回复
                </UiButton>
                <UiButton
                  v-if="session"
                  class="min-h-11"
                  size="sm"
                  variant="ghost"
                  @click="clearPrompt = true"
                >
                  <template #icon><Trash2 :size="15" /></template>清除对话
                </UiButton>
              </div>
            </div>

            <UiCard v-if="clearPrompt" padding="sm" class="space-y-3 border-danger/30 bg-danger/5">
              <p class="text-sm leading-relaxed text-ink">
                清除这段对话会先停止回复，并作废待确认建议。已批准的任务和长期偏好会保留。
              </p>
              <div class="flex flex-wrap gap-3">
                <UiButton class="min-h-11" variant="danger" @click="clear">确认清除</UiButton>
                <UiButton
                  class="min-h-11"
                  variant="ghost"
                  @click="clearPrompt = false"
                >取消</UiButton>
              </div>
            </UiCard>

            <UiButton
              v-if="olderOffset > 0"
              class="min-h-11 w-full"
              variant="ghost"
              @click="chat.loadOlder"
            >更早的消息</UiButton>

            <details class="group rounded-2xl border border-line/80 bg-surface/75 px-4 text-sm text-muted shadow-2xs transition-colors hover:border-line">
              <summary class="flex cursor-pointer select-none items-center justify-between gap-3 py-2.5 font-medium text-ink focus-ring rounded-lg">
                <span class="flex items-center gap-2 text-xs sm:text-sm">
                  <FolderOpen :size="15" class="shrink-0 text-accent" aria-hidden="true" />
                  <span>可用读取权限</span>
                </span>
                <span class="truncate text-xs text-subtle">{{ capabilities ? (readableRoots || '暂无可读目录') : '能力信息暂不可用' }}</span>
              </summary>
              <div class="border-t border-line/60 pb-3 pt-2.5 text-xs leading-relaxed text-subtle">
                <template v-if="capabilities">
                  <p>查询媒体、作者、文件目录、任务、日志和存储状态。</p>
                  <p class="mt-2">文件读取范围：{{ readableRoots || '暂无可读目录' }}</p>
                  <p class="mt-2">可提出资料修改、标签整理、维护任务与文件操作；每次批准只执行审批卡中列出的操作。</p>
                  <p v-if="!capabilities.image_analysis_supported" class="mt-2">可查看媒体预览；当前模型未分析图片、音视频内容。</p>
                </template>
                <p v-else>能力信息暂不可用，请稍后重新连接。</p>
              </div>
            </details>

            <ChatMessages
              :messages="messages"
              :disabled="!availability.enabled || sending"
              @suggest="useSuggestion"
            />

            <p
              v-if="toolStatus"
              role="status"
              class="inline-flex max-w-full items-center gap-2.5 rounded-full border border-accent/25 bg-accent/8 px-3.5 py-1.5 text-xs font-medium text-ink shadow-2xs"
            >
              <Loader2 v-if="active" :size="14" class="shrink-0 animate-spin text-accent motion-reduce:animate-none" />
              <span class="min-w-0 truncate">{{ toolStatus }}</span>
            </p>

            <MediaResults :results="results" @open="openMedia" />
            <ProjectResultCard :results="results" />

            <p v-if="truncated" class="text-sm text-muted">
              本轮部分结果超出展示上限，请缩小查询范围。
            </p>

            <section
              v-if="proposals.length"
              aria-label="待审阅建议"
              class="space-y-3.5"
            >
              <div class="flex items-center gap-2">
                <ShieldCheck :size="17" class="text-accent" aria-hidden="true" />
                <h2 class="font-semibold text-ink">整理建议</h2>
                <span class="rounded-full bg-accent/12 px-2 py-0.5 text-xs font-medium tabular-nums text-accent">
                  {{ proposals.length }}
                </span>
              </div>
              <ProposalCard
                v-for="proposal in proposals"
                :key="proposal.id"
                :proposal="proposal"
                :enabled="availability.enabled"
                @changed="approvalChanged"
              />
              <UiButton
                v-if="moreProposals"
                class="min-h-11 w-full"
                variant="ghost"
                @click="chat.loadMoreProposals"
              >更多建议</UiButton>
            </section>

            <p v-if="run" class="inline-flex flex-wrap items-center gap-1.5 rounded-xl bg-surface-2/70 px-3 py-1.5 text-xs text-subtle tabular-nums [overflow-wrap:anywhere]">
              用量：<template v-if="run.usage"
                >输入 {{ run.usage.input_tokens ?? '不可用' }} · 输出
                {{ run.usage.output_tokens ?? '不可用' }} · 合计
                {{ run.usage.total_tokens ?? '不可用' }} token</template
              ><template v-else>本轮不可用</template>
            </p>

            <div
              v-if="error || mediaError"
              role="alert"
              class="rounded-2xl border border-danger/30 bg-danger/5 p-3.5 text-sm text-danger [overflow-wrap:anywhere]"
            >
              {{ error || mediaError }}
              <UiButton
                v-if="hasRetry"
                class="mt-3 min-h-11"
                :disabled="sending"
                @click="chat.retrySend"
              >重试原消息</UiButton>
            </div>

            <form
              class="assistant-composer min-w-0 rounded-2xl border border-line/90 bg-surface/95 p-2.5 shadow-md backdrop-blur-md transition-all duration-150 focus-within:border-accent/45 focus-within:ring-4 focus-within:ring-accent/10"
              @submit.prevent="send"
            >
              <label for="assistant-input" class="sr-only">发送消息</label>
              <textarea
                id="assistant-input"
                ref="input"
                v-model="draft"
                rows="3"
                maxlength="8000"
                :disabled="
                  !availability.enabled ||
                  sending ||
                  session?.state === 'deleting'
                "
                aria-describedby="assistant-input-hint"
                class="block max-h-[40vh] min-h-[4.5rem] w-full min-w-0 resize-y rounded-xl bg-transparent px-3 py-2 text-sm leading-relaxed text-ink placeholder:text-muted focus:outline-none"
                placeholder="告诉管家你想找什么，例如：找一些温馨、还没看过的短篇漫画"
                @focus="keepComposerVisible"
                @keydown="key"
              />
              <div
                class="flex flex-wrap items-center justify-between gap-3 border-t border-line/60 px-2.5 pt-2.5"
              >
                <p id="assistant-input-hint" class="text-xs text-subtle tabular-nums">
                  {{ draft.length }}/8000 · Ctrl/⌘ + Enter 发送
                </p>
                <UiButton
                  class="min-h-11 px-5 shadow-2xs"
                  type="submit"
                  variant="primary"
                  :loading="sending"
                  :disabled="!canSend || !draft.trim()"
                >
                  <template #icon><Send :size="16" /></template>发送
                </UiButton>
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
    <ApprovalPanel
      v-if="allowed"
      v-model:open="approvalOpen"
      :items="approvalItems"
      :pending-count="pendingCount"
      :tab="approvalTab"
      :busy="approvalBusy"
      :error="approvalError"
      :has-more="approvalHasMore"
      :enabled="availability.enabled"
      @tab="approvalTab = $event"
      @refresh="approvals.refresh"
      @more="loadMoreApprovals"
      @changed="approvalChanged"
      @jump="jumpToProposal"
    />
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
.assistant-history-list {
  max-height: 320px;
}
@media (min-width: 1024px) {
  .assistant-history {
    position: sticky;
    top: 1.5rem;
    display: flex;
    flex-direction: column;
    min-height: min(640px, calc(100dvh - 210px));
  }
  .assistant-history-list {
    max-height: max(240px, calc(100dvh - 330px));
  }
}
.assistant-composer {
  scroll-margin-block: 1rem;
  padding-bottom: max(0.75rem, env(safe-area-inset-bottom));
}
:global(.he-app-shell:has(.he-assistant-page textarea:focus) .he-back-top) {
  display: none;
}
</style>
