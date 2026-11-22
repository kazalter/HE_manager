<script setup lang="ts">
import { Sparkles, BookOpen, Heart, Compass, BarChart3, ArrowUpRight } from 'lucide-vue-next'
import type { Component } from 'vue'
import type { MessageDTO } from '../../types/assistant'
defineProps<{ messages: MessageDTO[]; disabled?: boolean }>()
const emit = defineEmits<{ suggest: [text: string] }>()
const suggestions: { text: string; tag: string; icon: Component }[] = [
  { text: '找一些温馨、还没看过的短篇漫画', tag: '精准检索', icon: BookOpen },
  { text: '最近收藏了哪些视频？', tag: '收藏回顾', icon: Heart },
  { text: '按我的口味推荐几部漫画', tag: '猜你喜欢', icon: Compass },
  { text: '媒体库现在有多少作品？', tag: '库内概览', icon: BarChart3 },
]
const waiting = ['running', 'submitting', 'submission_unknown', 'stopping', 'reconciling']
</script>
<template>
  <div v-if="!messages.length" class="mx-auto max-w-2xl px-1 py-8 text-center text-muted sm:py-12">
    <span
      class="mx-auto mb-5 grid size-14 place-items-center rounded-2xl border border-accent/25 bg-accent/12 text-accent shadow-[0_8px_28px_-8px_rgb(var(--color-accent)/0.45)]"
      aria-hidden="true"
    >
      <Sparkles :size="24" />
    </span>
    <h2 class="text-lg font-semibold tracking-tight text-ink sm:text-xl">想从媒体库中发现什么？</h2>
    <p class="mt-2 text-sm leading-relaxed text-subtle sm:text-base">
      可以找作品、按喜好推荐，或提出标签与资料整理建议。
    </p>
    <p class="mt-1 text-xs text-subtle">资料修改和扫描都需要你在建议卡上确认。</p>
    <div class="mt-7 grid grid-cols-1 gap-2.5 text-left sm:grid-cols-2">
      <button
        v-for="item in suggestions"
        :key="item.text"
        type="button"
        :disabled="disabled"
        class="group flex min-h-14 items-start gap-3 rounded-2xl border border-line bg-surface-2/65 p-3.5 text-left transition-[transform,border-color,background-color,box-shadow] duration-150 hover:-translate-y-0.5 hover:border-accent/40 hover:bg-surface-2 hover:shadow-[var(--he-shadow-card)] focus-ring disabled:cursor-not-allowed disabled:opacity-50 disabled:hover:translate-y-0 motion-reduce:transition-none motion-reduce:hover:translate-y-0"
        @click="emit('suggest', item.text)"
      >
        <span class="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl bg-accent/10 text-accent transition-colors duration-150 group-hover:bg-accent/18 motion-reduce:transition-none" aria-hidden="true">
          <component :is="item.icon" :size="16" />
        </span>
        <span class="min-w-0 flex-1">
          <span class="block text-[11px] font-medium text-subtle">{{ item.tag }}</span>
          <span class="mt-0.5 block text-sm font-medium leading-snug text-ink">{{ item.text }}</span>
        </span>
        <ArrowUpRight :size="15" class="mt-1 shrink-0 text-subtle opacity-60 transition-[transform,opacity,color] duration-150 group-hover:translate-x-0.5 group-hover:-translate-y-0.5 group-hover:text-accent group-hover:opacity-100 motion-reduce:transition-none" aria-hidden="true" />
      </button>
    </div>
  </div>
  <div
    v-else
    role="log"
    aria-label="聊天记录"
    aria-live="off"
    class="space-y-4 sm:space-y-5"
  >
    <article
      v-for="message in messages"
      :key="message.id"
      :data-message-id="message.id"
      class="assistant-msg flex min-w-0 gap-3"
      :class="message.role === 'user' ? 'justify-end pl-6 sm:pl-16' : 'pr-2 sm:pr-12'"
    >
      <span
        v-if="message.role !== 'user'"
        class="mt-0.5 grid size-8 shrink-0 place-items-center rounded-xl border border-accent/25 bg-accent/12 text-accent shadow-[0_2px_10px_-3px_rgb(var(--color-accent)/0.35)]"
        aria-hidden="true"
      >
        <Sparkles :size="15" />
      </span>
      <div
        class="min-w-0 rounded-2xl px-4 py-3 transition-colors duration-150"
        :class="
          message.role === 'user'
            ? 'max-w-[min(86%,42rem)] rounded-tr-sm border border-accent/25 bg-accent/12 shadow-[0_2px_12px_-4px_rgb(var(--color-accent)/0.2)]'
            : 'max-w-full flex-1 rounded-tl-sm border border-line bg-surface-2/75 shadow-[0_1px_3px_rgb(0_0_0/0.06)]'
        "
      >
        <div
          class="mb-1.5 flex items-center gap-2 text-xs font-semibold text-muted"
          :class="{ 'sr-only': message.role === 'user' }"
        >
          <span>{{ message.role === 'user' ? '你' : '媒体库管家' }}</span>
          <span
            v-if="message.role !== 'user' && waiting.includes(message.status)"
            class="inline-flex items-center gap-1 rounded-full bg-accent/12 px-2 py-0.5 text-[11px] font-medium text-accent-glow"
          >
            处理中
          </span>
        </div>
        <p
          class="whitespace-pre-wrap text-[0.95rem] leading-relaxed [overflow-wrap:anywhere]"
          :class="message.content ? 'text-ink' : 'text-muted'"
        >
          <template v-if="message.content">{{ message.content }}</template>
          <template v-else-if="waiting.includes(message.status)">
            <span class="assistant-typing inline-flex items-center gap-1 align-middle text-accent" aria-hidden="true"><i></i><i></i><i></i></span>
            <span class="ml-2 text-sm text-muted">正在等待回复…</span>
          </template>
          <template v-else><span class="text-sm text-subtle">本轮没有回复文本</span></template>
        </p>
      </div>
    </article>
  </div>
</template>
<style scoped>
.assistant-msg {
  animation: assistant-msg-in 220ms var(--ease-snappy) both;
}
@keyframes assistant-msg-in {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}
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
  40% { opacity: 0.95; transform: translateY(-2.5px); }
}
@media (prefers-reduced-motion: reduce) {
  .assistant-msg { animation: none; }
  .assistant-typing i { animation: none; }
}
</style>
