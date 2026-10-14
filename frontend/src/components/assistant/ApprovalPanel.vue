<script setup lang="ts">
import { UiModal, UiButton } from '../ui'
import ProposalCard from './ProposalCard.vue'
import type { ProposalDTO } from '../../types/assistant'
const open = defineModel<boolean>('open', { required: true })
defineProps<{ items: ProposalDTO[]; pendingCount: number; tab: 'pending' | 'history'; busy: boolean; error: string | null; hasMore: boolean; enabled: boolean }>()
const emit = defineEmits<{ tab: [value: 'pending' | 'history']; refresh: []; more: []; changed: []; jump: [proposal: ProposalDTO] }>()
</script>
<template>
  <UiModal v-model:open="open" title="操作审批" description="先查看变更，批准后才会执行。" placement="right">
    <div
      class="sticky top-0 z-10 mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl border border-line/70 bg-surface-2/90 p-1.5 backdrop-blur-md"
      role="group"
      aria-label="审批列表"
    >
      <div class="flex flex-wrap items-center gap-1.5">
        <UiButton
          class="min-h-10"
          size="sm"
          :variant="tab === 'pending' ? 'primary' : 'ghost'"
          :aria-pressed="tab === 'pending'"
          @click="emit('tab', 'pending')"
        >
          待处理 ({{ pendingCount }})
        </UiButton>
        <UiButton
          class="min-h-10"
          size="sm"
          :variant="tab === 'history' ? 'primary' : 'ghost'"
          :aria-pressed="tab === 'history'"
          @click="emit('tab', 'history')"
        >
          已处理
        </UiButton>
      </div>
      <UiButton
        class="min-h-10"
        size="sm"
        variant="ghost"
        :disabled="busy"
        @click="emit('refresh')"
      >
        刷新
      </UiButton>
    </div>
    <p v-if="error" role="alert" class="mb-4 rounded-xl border border-danger/30 bg-danger/5 p-3 text-sm text-danger">
      {{ error }}
    </p>
    <p
      v-if="!items.length"
      role="status"
      class="rounded-2xl border border-dashed border-line/80 bg-surface-2/30 px-5 py-12 text-center text-sm text-muted"
    >
      {{ busy ? '正在加载审批…' : '目前没有相应的审批单。' }}
    </p>
    <div class="space-y-4">
      <section v-for="proposal in items" :key="proposal.id" class="min-w-0 space-y-1.5">
        <button
          type="button"
          class="inline-flex min-h-9 max-w-full items-center gap-1.5 rounded-lg bg-surface-2/80 px-2.5 py-1 text-left text-xs font-medium text-muted transition-colors hover:bg-surface-3 hover:text-ink focus-ring"
          @click="emit('jump', proposal)"
        >
          <span class="truncate">ID: {{ proposal.id }} · {{ proposal.target_label }}</span>
        </button>
        <ProposalCard :proposal="proposal" :enabled="enabled" @changed="emit('changed')" />
      </section>
    </div>
    <UiButton v-if="hasMore" class="mt-4 min-h-11 w-full" variant="ghost" :disabled="busy" @click="emit('more')">
      加载更多
    </UiButton>
  </UiModal>
</template>
