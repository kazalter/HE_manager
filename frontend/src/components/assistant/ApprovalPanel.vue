<script setup lang="ts">
import { RefreshCw, ShieldCheck, ArrowUpRight } from 'lucide-vue-next'
import { UiModal, UiButton, UiSegmented } from '../ui'
import ProposalCard from './ProposalCard.vue'
import type { ProposalDTO } from '../../types/assistant'
const open = defineModel<boolean>('open', { required: true })
defineProps<{ items: ProposalDTO[]; pendingCount: number; tab: 'pending' | 'history'; busy: boolean; error: string; hasMore: boolean; enabled: boolean }>()
const emit = defineEmits<{ tab: [value: 'pending' | 'history']; refresh: []; more: []; changed: []; jump: [proposal: ProposalDTO] }>()
</script>
<template>
  <UiModal v-model:open="open" title="操作审批" description="先查看变更，批准后才会执行。" placement="right">
    <div class="sticky top-0 z-10 -mx-1 mb-4 flex flex-wrap items-center justify-between gap-2 border-b border-line/80 bg-surface-2/95 px-1 pb-3 pt-1 backdrop-blur-md">
      <UiSegmented
        :model-value="tab"
        label="审批列表"
        size="sm"
        :options="[
          { value: 'pending', label: `待审批 · ${pendingCount}` },
          { value: 'history', label: '执行记录' },
        ]"
        @update:model-value="emit('tab', $event as 'pending' | 'history')"
      />
      <UiButton class="min-h-9" size="sm" variant="ghost" :disabled="busy" :loading="busy" @click="emit('refresh')">
        <template #icon><RefreshCw :size="14" /></template>刷新
      </UiButton>
    </div>
    <p v-if="error" role="alert" class="mb-4 rounded-xl border border-danger/30 bg-danger/8 px-3 py-2 text-sm text-danger">{{ error }}</p>
    <div v-if="!items.length" role="status" class="rounded-2xl border border-dashed border-line bg-surface-2/40 px-5 py-10 text-center">
      <span class="mx-auto mb-3 grid size-10 place-items-center rounded-xl bg-accent/10 text-accent" aria-hidden="true">
        <ShieldCheck :size="19" />
      </span>
      <p class="text-sm leading-relaxed text-muted">
        {{ busy ? '正在加载审批…' : tab === 'pending' ? '没有待审批操作。管家提出修改时，会在这里等待你确认。' : '还没有操作记录。' }}
      </p>
    </div>
    <div class="space-y-4">
      <section v-for="proposal in items" :key="proposal.id" class="min-w-0">
        <button
          type="button"
          class="mb-2 inline-flex min-h-8 max-w-full items-center gap-1.5 rounded-full border border-line bg-surface-2/80 px-3 py-1 text-left text-xs font-medium text-muted transition-colors duration-150 hover:border-accent/35 hover:text-ink focus-ring [overflow-wrap:anywhere]"
          @click="emit('jump', proposal)"
        >
          <span class="truncate">{{ proposal.session_title || '查看所属对话' }}</span>
          <ArrowUpRight :size="13" class="shrink-0" aria-hidden="true" />
        </button>
        <ProposalCard :proposal="proposal" :enabled="enabled" @changed="emit('changed')" />
      </section>
    </div>
    <UiButton v-if="hasMore" class="mt-4 min-h-11 w-full" variant="ghost" :disabled="busy" @click="emit('more')">加载更多</UiButton>
  </UiModal>
</template>
