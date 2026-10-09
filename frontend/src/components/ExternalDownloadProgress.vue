<script setup lang="ts">
import { computed } from 'vue'
import { X } from 'lucide-vue-next'
import { UiButton } from './ui'
import { externalDownloadStore } from '../stores/externalDownloadStore'

const job = externalDownloadStore.job
const inProgress = externalDownloadStore.inProgress
const totalBooks = externalDownloadStore.totalBooks
const successBooks = externalDownloadStore.successBooks
const failedBooks = externalDownloadStore.failedBooks
const totalPages = externalDownloadStore.totalPages
const downloadedPages = externalDownloadStore.downloadedPages
const currentBookTitle = externalDownloadStore.currentBookTitle
const currentBookTotalPages = externalDownloadStore.currentBookTotalPages
const currentBookDownloadedPages = externalDownloadStore.currentBookDownloadedPages
const progressPercent = externalDownloadStore.progressPercent
const canCancel = externalDownloadStore.canCancel
const tasks = externalDownloadStore.tasks

const statusLabel = computed(() => {
  if (!job.value) return ''
  const map: Record<string, string> = {
    running: '下载中',
    preparing: '准备中',
    completed: '已完成',
    failed: '失败',
    canceled: '已取消',
    canceling: '取消中',
  }
  return map[job.value.status] || job.value.status
})

const statusBookText = computed(() => {
  if (!job.value) return ''
  return `${successBooks.value}/${totalBooks.value} 本完成 · ${failedBooks.value} 失败`
})

const cancelText = computed(() => {
  if (!job.value) return '取消下载'
  return job.value.status === 'canceling' || job.value.cancel_requested ? '取消中' : '取消下载'
})

const taskLabel = (status: string) => (
  status === 'success' ? '成功' : status === 'failed' ? '失败' : status === 'downloading' ? '下载中' : '等待'
)
const taskTone = (status: string) => (
  status === 'success' ? 'text-success' : status === 'failed' ? 'text-danger' : status === 'downloading' ? 'text-accent-glow' : 'text-subtle'
)

const onCancel = () => externalDownloadStore.cancelDownload()
</script>

<template>
  <div v-if="job" class="space-y-3 rounded-2xl border border-line bg-surface p-4">
    <div class="flex items-start justify-between gap-3">
      <div class="min-w-0">
        <p class="text-body font-medium text-ink">
          {{ statusLabel }}
          <span class="text-meta font-normal text-subtle tabular-nums">· {{ statusBookText }}</span>
        </p>
        <p class="mt-0.5 text-meta text-subtle tabular-nums">
          {{ downloadedPages }} / {{ totalPages }} 页 · {{ progressPercent }}%
        </p>
      </div>
      <UiButton v-if="inProgress" size="sm" variant="ghost" class="hover:!bg-danger/12 hover:!text-danger" :disabled="!canCancel" @click="onCancel">
        <template #icon><X :size="14" aria-hidden="true" /></template>
        {{ cancelText }}
      </UiButton>
    </div>

    <div class="h-1 overflow-hidden rounded-sm bg-surface-3" role="progressbar" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100" aria-label="下载进度">
      <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: `${progressPercent}%` }"></div>
    </div>

    <div v-if="currentBookTitle" class="min-w-0 text-meta text-subtle">
      <p class="truncate">正在下载：<span class="font-medium text-ink">{{ currentBookTitle }}</span></p>
      <p class="tabular-nums">当前漫画 {{ currentBookDownloadedPages }} / {{ currentBookTotalPages }} 页</p>
    </div>

    <ul v-if="tasks.length" class="max-h-40 space-y-1 overflow-y-auto border-t border-line pt-3 pr-1">
      <li v-for="task in tasks" :key="task.id" class="flex min-w-0 items-center gap-2 text-caption">
        <span class="w-12 shrink-0 font-medium" :class="taskTone(task.status)">{{ taskLabel(task.status) }}</span>
        <span class="min-w-0 truncate text-muted">{{ task.title || `#${task.item_id}` }}</span>
        <span v-if="task.total_pages" class="shrink-0 text-subtle tabular-nums">{{ task.downloaded_pages }}/{{ task.total_pages }}</span>
        <span v-if="task.error" class="min-w-0 shrink truncate text-danger">· {{ task.error }}</span>
      </li>
    </ul>
  </div>
</template>
