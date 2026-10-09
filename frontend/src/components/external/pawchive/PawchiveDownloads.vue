<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Download, RefreshCw, RotateCcw, Square } from 'lucide-vue-next'
import { EmptyState, SectionHeader, UiBadge, UiButton, UiSpinner, buttonClass, type Tone } from '../../ui'
import type { PawchiveDownloadJob } from '../../../types/pawchive'
import { cancelPawchiveDownload, getPawchiveDownload, listPawchiveDownloads, pawchiveError, retryPawchiveDownload } from '../../../utils/pawchiveApi'

const props = defineProps<{ refreshKey: number }>()
const jobs = ref<PawchiveDownloadJob[]>([])
const details = ref<Record<string, PawchiveDownloadJob>>({})
const loading = ref(false)
const error = ref('')
let timer: number | undefined

const STATUS: Record<string, { label: string; tone: Tone }> = {
  queued: { label: '排队中', tone: 'neutral' },
  preparing: { label: '准备中', tone: 'info' },
  running: { label: '下载中', tone: 'info' },
  canceling: { label: '取消中', tone: 'warning' },
  completed: { label: '已完成', tone: 'success' },
  failed: { label: '失败', tone: 'danger' },
  canceled: { label: '已取消', tone: 'warning' },
  interrupted: { label: '已中断', tone: 'warning' },
  pending: { label: '等待中', tone: 'neutral' },
  downloading: { label: '下载中', tone: 'info' },
  skipped: { label: '已跳过', tone: 'neutral' },
}
const statusOf = (status: string) => STATUS[status] || { label: status, tone: 'neutral' as Tone }
const percent = (job: PawchiveDownloadJob) => job.total ? Math.round((job.completed + job.failed + job.canceled) / job.total * 100) : 0

const refresh = async () => {
  loading.value = true
  try {
    jobs.value = await listPawchiveDownloads()
    error.value = ''
    for (const jobId of Object.keys(details.value)) {
      details.value[jobId] = await getPawchiveDownload(jobId)
    }
  } catch (cause) { error.value = pawchiveError(cause) }
  finally { loading.value = false }
}
const toggleDetails = async (jobId: string) => {
  if (details.value[jobId]) { const copy = { ...details.value }; delete copy[jobId]; details.value = copy; return }
  try { details.value = { ...details.value, [jobId]: await getPawchiveDownload(jobId) } }
  catch (cause) { error.value = pawchiveError(cause) }
}
const cancel = async (jobId: string) => {
  try { await cancelPawchiveDownload(jobId); await refresh() }
  catch (cause) { error.value = pawchiveError(cause) }
}
const retry = async (jobId: string) => {
  try { await retryPawchiveDownload(jobId); await refresh() }
  catch (cause) { error.value = pawchiveError(cause) }
}
watch(() => props.refreshKey, () => { void refresh() })
onMounted(() => { void refresh(); timer = window.setInterval(() => {
  if (jobs.value.some(job => ['queued', 'preparing', 'running', 'canceling'].includes(job.status))) void refresh()
}, 3000) })
onBeforeUnmount(() => window.clearInterval(timer))
</script>

<template>
  <section class="space-y-3">
    <SectionHeader title="Pawchive 下载" description="只记录明确提交的下载，已完成的文件可在媒体库打开。">
      <template #actions>
        <UiButton size="sm" variant="ghost" :loading="loading && !!jobs.length" @click="refresh">
          <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
          刷新
        </UiButton>
      </template>
    </SectionHeader>
    <p v-if="error" role="alert" class="rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">{{ error }}</p>
    <p v-if="loading && !jobs.length" role="status" class="flex items-center justify-center gap-2 py-12 text-meta text-subtle"><UiSpinner :size="16" />读取任务…</p>
    <div v-else-if="!jobs.length" class="rounded-2xl border border-dashed border-line">
      <EmptyState compact :icon="Download" title="暂无下载任务" description="在作者作品里勾选帖子，或在查看器里下载当前图片。" />
    </div>
    <div v-else class="divide-y divide-line overflow-hidden rounded-2xl border border-line bg-surface">
      <article v-for="job in jobs" :key="job.job_id" class="space-y-3 px-4 py-4 sm:px-5">
        <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-2">
          <div class="min-w-0 flex-1">
            <h3 class="truncate text-body font-medium text-ink">{{ job.message || `任务 ${job.job_id.slice(0, 8)}` }}</h3>
            <p class="mt-1 flex flex-wrap items-center gap-2 text-caption text-subtle">
              <UiBadge :tone="statusOf(job.status).tone">{{ statusOf(job.status).label }}</UiBadge>
              <span class="tabular-nums">完成 {{ job.completed }} · 失败 {{ job.failed }} · 取消 {{ job.canceled }} · 共 {{ job.total }}</span>
              <span class="font-mono text-faint">{{ job.job_id.slice(0, 8) }}</span>
            </p>
          </div>
          <div class="flex flex-wrap items-center gap-1">
            <UiButton v-if="['queued', 'running', 'canceling'].includes(job.status)" size="sm" variant="ghost" class="hover:!bg-danger/12 hover:!text-danger" @click="cancel(job.job_id)">
              <template #icon><Square :size="13" aria-hidden="true" /></template>
              取消
            </UiButton>
            <UiButton v-if="['failed', 'canceled', 'interrupted'].includes(job.status)" size="sm" @click="retry(job.job_id)">
              <template #icon><RotateCcw :size="13" aria-hidden="true" /></template>
              重试
            </UiButton>
            <UiButton size="sm" variant="ghost" :aria-expanded="!!details[job.job_id]" @click="toggleDetails(job.job_id)">附件明细</UiButton>
          </div>
        </div>
        <div class="h-1 overflow-hidden rounded-sm bg-surface-3" role="progressbar" :aria-valuenow="job.completed + job.failed + job.canceled" aria-valuemin="0" :aria-valuemax="job.total">
          <div class="h-full rounded-sm bg-accent" :style="{ width: `${percent(job)}%` }"></div>
        </div>
        <ul v-if="details[job.job_id]" class="divide-y divide-line overflow-hidden rounded-lg border border-line">
          <li v-for="attachment in details[job.job_id]?.attachments || []" :key="attachment.attachment_key" class="flex flex-wrap items-center justify-between gap-2 px-3 py-2 text-meta">
            <span class="min-w-0 flex-1 break-all text-muted">
              {{ attachment.filename }}
              <UiBadge class="ml-1 align-middle" :tone="statusOf(attachment.status).tone">{{ statusOf(attachment.status).label }}</UiBadge>
              <span v-if="attachment.error" class="text-danger"> · {{ attachment.error }}</span>
            </span>
            <router-link v-if="attachment.media_id" :to="{ path: '/', query: { media: attachment.media_id } }" :class="buttonClass('secondary', 'sm')">打开本地媒体</router-link>
          </li>
        </ul>
      </article>
    </div>
  </section>
</template>
