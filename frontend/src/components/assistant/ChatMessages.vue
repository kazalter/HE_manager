<script setup lang="ts">
import { Sparkles, ArrowUpRight } from 'lucide-vue-next'
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
  <div
    v-if="!messages.length"
    class="rounded-2xl border border-line/80 bg-surface/75 px-4 py-10 text-center text-muted shadow-2xs backdrop-blur-sm sm:px-8 sm:py-12"
  >
    <span class="mx-auto mb-4 grid size-14 place-items-center rounded-2xl bg-accent/12 text-accent ring-1 ring-accent/25 shadow-2xs">
      <Sparkles :size="24" aria-hidden="true" />
    </span>
    <h2 class="text-lg font-semibold text-ink sm:text-xl">想从媒体库中发现什么？</h2>
    <p class="mt-2 text-sm leading-relaxed text-muted">
      可以找作品、按喜好推荐，或提出标签与资料整理建议。
    </p>
    <p class="mt-1 text-xs text-subtle">资料修改和扫描都需要你在建议卡上确认。</p>
    <div class="mx-auto mt-6 grid max-w-2xl grid-cols-1 gap-2.5 sm:grid-cols-2">
      <button
        v-for="text in suggestions"
        :key="text"
        type="button"
        :disabled="disabled"
        class="group flex min-h-12 items-center justify-between gap-3 rounded-xl border border-line/80 bg-surface px-4 py-3 text-left text-sm text-ink shadow-2xs transition-all duration-150 hover:-translate-y-0.5 hover:border-accent/40 hover:bg-surface-3/60 focus-ring disabled:opacity-50 disabled:hover:translate-y-0"
        @click="emit('suggest', text)"
      >
        <span class="line-clamp-2 font-medium">{{ text }}</span>
        <ArrowUpRight
          :size="16"
          class="shrink-0 text-subtle transition-transform duration-150 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-accent"
          aria-hidden="true"
        />
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
        class="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-accent/12 text-accent ring-1 ring-accent/20 shadow-2xs"
        aria-hidden="true"
      >
        <Sparkles :size="16" />
      </span>
      <div
        class="min-w-0 rounded-2xl px-4 py-3.5 shadow-2xs transition-colors"
        :class="
          message.role === 'user'
            ? 'rounded-tr-sm border border-accent/25 bg-accent/12'
            : 'rounded-tl-sm border border-line/80 bg-surface/95'
        "
      >
        <h3
          class="mb-1.5 flex items-center gap-1.5 text-xs font-semibold text-muted"
          :class="{ 'sr-only': message.role === 'user' }"
        >
          {{ message.role === 'user' ? '你' : '媒体库管家' }}
        </h3>
        <p
          class="whitespace-pre-wrap text-sm leading-relaxed [overflow-wrap:anywhere]"
          :class="message.content ? 'text-ink' : 'text-muted'"
        >
          <template v-if="message.content">{{ message.content }}</template>
          <template v-else-if="waiting.includes(message.status)">
            <span class="assistant-typing inline-flex items-center gap-1 align-middle" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="ml-2">正在等待回复...</span>
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
