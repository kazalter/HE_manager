<script setup lang="ts">
import { computed, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import {
  MessageSquare,
  Plus,
  Send,
  Square,
  RefreshCw,
  Trash2,
} from 'lucide-vue-next'
import { authState } from '../auth'
import { API_BASE_URL } from '../config'
import { PageHeader, UiButton, UiCard } from '../components/ui'
import ChatMessages from '../components/assistant/ChatMessages.vue'
import MediaResults from '../components/assistant/MediaResults.vue'
import ProposalCard from '../components/assistant/ProposalCard.vue'
import { AsyncMediaDetail as MediaDetail } from '../components/asyncComponents'
import { useAssistantChat } from '../composables/useAssistantChat'
import type { Media } from '../types'
const chat = useAssistantChat()
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
  await chat.send(draft.value)
  if (run.value && !hasRetry.value) draft.value = ''
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
  window.visualViewport?.addEventListener('resize', keepComposerVisible)
  window.addEventListener('resize', keepComposerVisible)
})
watch(
  () => authState.token,
  () => {
    selectedMedia.value = null
    clearPrompt.value = false
  },
)
onBeforeUnmount(() => {
  alive = false
  cancelAnimationFrame(focusFrame)
  window.visualViewport?.removeEventListener('resize', keepComposerVisible)
  window.removeEventListener('resize', keepComposerVisible)
})
</script>
<template>
  <div class="he-assistant-page min-w-0 min-h-full">
    <PageHeader title="媒体库管家" description="搜索、推荐与整理；变更由你确认">
      <template #leading
        ><MessageSquare :size="24" class="text-accent" aria-hidden="true"
      /></template>
      <template v-if="allowed" #actions
        ><UiButton
          class="min-h-11"
          :disabled="!availability.enabled || loading || sending"
          @click="chat.newSession"
          ><template #icon><Plus :size="16" /></template>新对话</UiButton
        ></template
      >
    </PageHeader>
    <div class="page-gutter pb-8">
      <div v-if="!allowed" class="page-container text-muted">
        此功能仅向管理员开放。
      </div>
      <div v-else class="page-container min-w-0">
        <div
          class="mx-auto grid max-w-[1100px] min-w-0 gap-5 lg:grid-cols-[220px_minmax(0,1fr)]"
        >
          <UiCard padding="sm" class="min-w-0 self-start">
            <label
              for="assistant-session"
              class="mb-2 block text-sm font-medium text-ink"
              >对话历史</label
            >
            <select
              id="assistant-session"
              :value="session?.id || ''"
              class="min-h-11 w-full min-w-0 rounded-xl border border-line bg-surface px-3 text-ink focus-ring"
              :disabled="loading || sending"
              @change="
                chat.selectSession(
                  sessions.find(
                    (s) => s.id === ($event.target as HTMLSelectElement).value,
                  )!,
                )
              "
            >
              <option value="" disabled>选择对话</option>
              <option v-for="item in sessions" :key="item.id" :value="item.id">
                {{ item.title
                }}{{ item.state === 'deleting' ? ' · 正在清除' : '' }}
              </option>
            </select>
            <UiButton
              v-if="moreSessions"
              class="mt-3 min-h-11"
              @click="chat.loadMoreSessions"
              >更多历史</UiButton
            >
            <p v-if="!availability.enabled" class="mt-3 text-sm text-muted">
              管家暂未启用，历史和停止操作仍可使用。
            </p>
            <p class="mt-3 text-sm leading-relaxed text-muted">
              修改标签、资料和启动扫描都需要确认。管家只能查询媒体元数据。
            </p>
          </UiCard>
          <div class="min-w-0 space-y-5">
            <div
              class="flex min-w-0 flex-wrap items-center justify-between gap-3"
            >
              <p role="status" aria-live="polite" class="text-sm text-muted">
                {{ loading ? '正在加载…' : status
                }}<span v-if="active && !connected"> · 未连接</span>
              </p>
              <div class="flex flex-wrap gap-2">
                <UiButton
                  v-if="run"
                  class="min-h-11"
                  size="sm"
                  @click="chat.reconnect"
                  ><template #icon><RefreshCw :size="15" /></template
                  >重新连接</UiButton
                ><UiButton
                  v-if="active"
                  class="min-h-11"
                  size="sm"
                  @click="chat.stop"
                  ><template #icon><Square :size="15" /></template
                  >停止回复</UiButton
                ><UiButton
                  v-if="session"
                  class="min-h-11"
                  size="sm"
                  @click="clearPrompt = true"
                  ><template #icon><Trash2 :size="15" /></template
                  >清除对话</UiButton
                >
              </div>
            </div>
            <UiCard v-if="clearPrompt" padding="sm" class="space-y-3"
              ><p class="text-ink">
                清除这段对话会先停止回复，并作废待确认建议。已确认的扫描和长期偏好会保留。
              </p>
              <div class="flex flex-wrap gap-3">
                <UiButton class="min-h-11" @click="clear">确认清除</UiButton
                ><UiButton
                  class="min-h-11"
                  variant="ghost"
                  @click="clearPrompt = false"
                  >取消</UiButton
                >
              </div></UiCard
            >
            <UiButton
              v-if="olderOffset > 0"
              class="min-h-11"
              @click="chat.loadOlder"
              >更早的消息</UiButton
            >
            <ChatMessages :messages="messages" />
            <p v-if="toolStatus" class="text-sm text-muted">{{ toolStatus }}</p>
            <MediaResults :results="results" @open="openMedia" />
            <p v-if="truncated" class="text-sm text-muted">
              本轮部分结果超出展示上限，请缩小查询范围。
            </p>
            <section
              v-if="proposals.length"
              aria-label="待审阅建议"
              class="space-y-3"
            >
              <h2 class="font-semibold text-ink">整理建议</h2>
              <ProposalCard
                v-for="proposal in proposals"
                :key="proposal.id"
                :proposal="proposal"
                :enabled="availability.enabled"
                @changed="chat.refreshProposals"
              /><UiButton
                v-if="moreProposals"
                class="min-h-11"
                @click="chat.loadMoreProposals"
                >更多建议</UiButton
              >
            </section>
            <p v-if="run" class="text-sm text-subtle [overflow-wrap:anywhere]">
              用量：<template v-if="run.usage"
                >输入 {{ run.usage.input_tokens ?? '不可用' }} · 输出
                {{ run.usage.output_tokens ?? '不可用' }} · 合计
                {{ run.usage.total_tokens ?? '不可用' }} token</template
              ><template v-else>本轮不可用</template>
            </p>
            <div
              v-if="error || mediaError"
              role="alert"
              class="rounded-xl border border-danger/30 bg-danger/5 p-3 text-sm text-danger [overflow-wrap:anywhere]"
            >
              {{ error || mediaError
              }}<UiButton
                v-if="hasRetry"
                class="mt-3 min-h-11"
                :disabled="sending"
                @click="chat.retrySend"
                >重试原消息</UiButton
              >
            </div>
            <form
              class="assistant-composer min-w-0 rounded-2xl border border-line bg-surface p-3 sm:p-4"
              @submit.prevent="send"
            >
              <label
                for="assistant-input"
                class="mb-2 block text-sm font-medium text-ink"
                >发送消息</label
              >
              <textarea
                ref="input"
                @focus="keepComposerVisible"
                id="assistant-input"
                v-model="draft"
                rows="3"
                maxlength="8000"
                :disabled="
                  !availability.enabled ||
                  sending ||
                  session?.state === 'deleting'
                "
                aria-describedby="assistant-input-hint"
                class="w-full min-w-0 resize-y rounded-xl border border-line bg-surface-2 p-3 text-base leading-relaxed text-ink focus-ring"
                placeholder="例如：找一些温馨、还没看过的短篇漫画"
                @keydown="key"
              />
              <div
                class="mt-3 flex flex-wrap items-center justify-between gap-3"
              >
                <p id="assistant-input-hint" class="text-sm text-muted">
                  {{ draft.length }}/8000 · Ctrl/⌘ + Enter 发送
                </p>
                <UiButton
                  class="min-h-11"
                  type="submit"
                  variant="primary"
                  :loading="sending"
                  :disabled="!canSend || !draft.trim()"
                  ><template #icon><Send :size="16" /></template>发送</UiButton
                >
              </div>
            </form>
          </div>
        </div>
      </div>
    </div>
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
.assistant-composer {
  scroll-margin-block: 1rem;
  padding-bottom: max(1rem, env(safe-area-inset-bottom));
}
:global(.he-app-shell:has(.he-assistant-page textarea:focus) .he-back-top) {
  display: none;
}
</style>
