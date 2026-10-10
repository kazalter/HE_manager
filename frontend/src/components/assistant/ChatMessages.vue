<script setup lang="ts">
import type { MessageDTO } from '../../types/assistant'
defineProps<{ messages: MessageDTO[] }>()
</script>
<template>
  <div v-if="!messages.length" class="py-12 text-center text-muted">
    <h2 class="text-lg font-medium text-ink">想从媒体库中发现什么？</h2>
    <p class="mt-3 leading-relaxed">
      可以找作品、按喜好推荐，或提出标签与资料整理建议。
    </p>
    <p class="mt-2 text-sm">资料修改和扫描都需要你在建议卡上确认。</p>
  </div>
  <div
    v-else
    role="log"
    aria-label="聊天记录"
    aria-live="off"
    class="space-y-5"
  >
    <article
      v-for="message in messages"
      :key="message.id"
      :data-message-id="message.id"
      class="min-w-0 rounded-2xl border border-line p-4"
      :class="
        message.role === 'user'
          ? 'ml-4 bg-surface-2 sm:ml-16'
          : 'mr-4 bg-surface sm:mr-16'
      "
    >
      <h3 class="mb-2 text-sm font-semibold text-muted">
        {{ message.role === 'user' ? '你' : '媒体库管家' }}
      </h3>
      <p
        class="whitespace-pre-wrap leading-relaxed text-ink [overflow-wrap:anywhere]"
      >
        {{
          message.content ||
          ([
            'running',
            'submitting',
            'submission_unknown',
            'stopping',
            'reconciling',
          ].includes(message.status)
            ? '正在等待回复…'
            : '本轮没有回复文本')
        }}
      </p>
    </article>
  </div>
</template>
