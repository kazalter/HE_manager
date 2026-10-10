<script setup lang="ts">
import { UiModal, UiButton } from '../ui'
import ProposalCard from './ProposalCard.vue'
import type { ProposalDTO } from '../../types/assistant'
const open = defineModel<boolean>('open', { required: true })
defineProps<{ items: ProposalDTO[]; pendingCount: number; tab: 'pending' | 'history'; busy: boolean; error: string; hasMore: boolean; enabled: boolean }>()
const emit = defineEmits<{ tab: [value: 'pending' | 'history']; refresh: []; more: []; changed: []; jump: [proposal: ProposalDTO] }>()
</script>
<template>
  <UiModal v-model:open="open" title="操作审批" description="先查看变更，批准后才会执行。" placement="right">
    <div class="sticky top-0 z-10 mb-4 flex flex-wrap gap-2 bg-surface-3 py-2" role="group" aria-label="审批列表">
      <UiButton class="min-h-11" :variant="tab === 'pending' ? 'primary' : 'ghost'" :aria-pressed="tab === 'pending'" @click="emit('tab', 'pending')">待审批 · {{ pendingCount }}</UiButton>
      <UiButton class="min-h-11" :variant="tab === 'history' ? 'primary' : 'ghost'" :aria-pressed="tab === 'history'" @click="emit('tab', 'history')">执行记录</UiButton>
      <UiButton class="min-h-11" variant="ghost" :disabled="busy" @click="emit('refresh')">刷新</UiButton>
    </div>
    <p v-if="error" role="alert" class="mb-4 text-sm text-danger">{{ error }}</p>
    <p v-if="!items.length" role="status" class="rounded-2xl border border-dashed border-line px-5 py-10 text-center text-sm leading-relaxed text-muted">{{ busy ? '正在加载审批…' : tab === 'pending' ? '没有待审批操作。管家提出修改时，会在这里等待你确认。' : '还没有操作记录。' }}</p>
    <div class="space-y-4">
      <section v-for="proposal in items" :key="proposal.id" class="min-w-0">
        <button type="button" class="mb-2 min-h-11 max-w-full rounded-lg px-1 text-left text-sm text-muted focus-ring [overflow-wrap:anywhere] hover:text-ink" @click="emit('jump', proposal)">{{ proposal.session_title || '查看所属对话' }} ↗</button>
        <ProposalCard :proposal="proposal" :enabled="enabled" @changed="emit('changed')" />
      </section>
    </div>
    <UiButton v-if="hasMore" class="mt-4 min-h-11 w-full" :disabled="busy" @click="emit('more')">加载更多</UiButton>
  </UiModal>
</template>
