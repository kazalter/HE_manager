<script setup lang="ts">
import { Sparkles } from 'lucide-vue-next'
import type { MessageDTO } from '../../types/assistant'
defineProps<{ messages: MessageDTO[]; disabled?: boolean }>()
const emit = defineEmits<{ suggest: [text: string] }>()
const suggestions = [
  '找一些温馨、还没看过的短篇漫画',
  '最近收藏了哪些视频？',
  '按我的口味推荐几部漫画',
  '媒体库现在有多少作品？',
]
const waiting = ['running', 'submitting', 'submission_unknown', 'stopping', 'reconciling']
</script>
<template>
  <div v-if="!messages.length" class="px-2 py-10 text-center text-muted sm:py-14">
    <span class="mx-auto mb-4 grid size-12 place-items-center rounded-2xl bg-accent/12 text-accent">
      <Sparkles :size="22" aria-hidden="true" />
    </span>
    <h2 class="text-lg font-medium text-ink">想从媒体库中发现什么？</h2>
    <p class="mt-2 leading-relaxed">
      可以找作品、按喜好推荐，或提出标签与资料整理建议。
    </p>
    <p class="mt-1 text-sm text-subtle">资料修改和扫描都需要你在建议卡上确认。</p>
    <div class="mx-auto mt-6 flex max-w-xl flex-wrap justify-center gap-2">
      <button
        v-for="text in suggestions"
        :key="text"
        type="button"
        :disabled="disabled"
        class="min-h-10 rounded-full border border-line bg-surface px-3.5 py-1.5 text-sm text-ink transition-colors duration-150 hover:border-accent/40 hover:bg-accent/10 focus-ring disabled:cursor-not-allowed disabled:opacity-50 motion-reduce:transition-none"
        @click="emit('suggest', text)"
      >
        {{ text }}
      </button>
    </div>
  </div>
  <div
    v-else
    role="log"
    aria-label="聊天记录"
    aria-live="off"
    class="space-y-4"
  >
    <article
      v-for="message in messages"
      :key="message.id"
      :data-message-id="message.id"
      class="flex min-w-0 gap-3"
      :class="message.role === 'user' ? 'justify-end pl-8 sm:pl-20' : 'pr-4 sm:pr-16'"
    >
      <span
        v-if="message.role !== 'user'"
        class="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-accent/12 text-accent"
        aria-hidden="true"
      >
        <Sparkles :size="16" />
      </span>
      <div
        class="min-w-0 rounded-2xl px-4 py-3"
        :class="
          message.role === 'user'
            ? 'rounded-tr-md border border-accent/20 bg-accent/10'
            : 'rounded-tl-md border border-line bg-surface'
        "
      >
        <h3
          class="mb-1 text-xs font-semibold text-muted"
          :class="{ 'sr-only': message.role === 'user' }"
        >
          {{ message.role === 'user' ? '你' : '媒体库管家' }}
        </h3>
        <p
          class="whitespace-pre-wrap leading-relaxed [overflow-wrap:anywhere]"
          :class="message.content ? 'text-ink' : 'text-muted'"
        >
          <template v-if="message.content">{{ message.content }}</template>
          <template v-else-if="waiting.includes(message.status)">
            <span class="assistant-typing inline-flex items-center gap-1 align-middle" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="ml-2">正在等待回复…</span>
          </template>
          <template v-else>本轮没有回复文本</template>
        </p>
      </div>
    </article>
  </div>
</template>
<style scoped>
.assistant-typing i {
  display: block;
  width: 6px;
  height: 6px;
  border-radius: 9999px;
  background: currentColor;
  opacity: 0.35;
  animation: assistant-typing 1.2s infinite ease-in-out;
}
.assistant-typing i:nth-child(2) { animation-delay: 0.15s; }
.assistant-typing i:nth-child(3) { animation-delay: 0.3s; }
@keyframes assistant-typing {
  0%, 80%, 100% { opacity: 0.25; transform: translateY(0); }
  40% { opacity: 0.9; transform: translateY(-2px); }
}
@media (prefers-reduced-motion: reduce) {
  .assistant-typing i { animation: none; }
}
</style>
