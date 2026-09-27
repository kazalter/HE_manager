<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Loader2, RotateCcw, Square } from 'lucide-vue-next'
import type { PawchiveDownloadJob } from '../../../types/pawchive'
import { cancelPawchiveDownload, getPawchiveDownload, listPawchiveDownloads, pawchiveError, retryPawchiveDownload } from '../../../utils/pawchiveApi'

const props = defineProps<{ refreshKey: number }>()
const jobs = ref<PawchiveDownloadJob[]>([])
const details = ref<Record<string, PawchiveDownloadJob>>({})
const loading = ref(false)
const error = ref('')
let timer: number | undefined

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
  <section class="space-y-4">
    <div class="flex items-center justify-between gap-3"><div><h2 class="text-lg font-bold text-white">Pawchive 下载</h2><p class="text-xs text-white/55">只记录明确提交的下载；已完成文件可在媒体库打开。</p></div><button type="button" class="min-h-11 px-4 rounded-xl border border-white/15 text-sm text-white cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="refresh">刷新</button></div>
    <p v-if="error" role="alert" class="text-sm text-red-300">{{ error }}</p>
    <p v-if="loading && !jobs.length" role="status" class="py-12 text-white/55 text-center flex items-center justify-center gap-2"><Loader2 :size="17" class="animate-spin" />读取任务…</p>
    <p v-else-if="!jobs.length" class="py-12 text-white/55 text-center">暂无下载任务。</p>
    <article v-for="job in jobs" :key="job.job_id" class="rounded-2xl border border-white/10 bg-white/[0.04] p-4 space-y-3">
      <div class="flex flex-wrap justify-between items-center gap-2"><div><h3 class="text-sm font-bold text-white">任务 {{ job.job_id.slice(0, 8) }}</h3><p class="text-xs text-white/60">{{ job.message }} · {{ job.status }}</p></div><div class="flex flex-wrap gap-2"><button v-if="['queued', 'running', 'canceling'].includes(job.status)" type="button" class="min-h-11 px-3 rounded-xl border border-white/15 text-xs text-white cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="cancel(job.job_id)"><Square :size="13" class="inline" /> 取消</button><button v-if="['failed', 'canceled', 'interrupted'].includes(job.status)" type="button" class="min-h-11 px-3 rounded-xl border border-white/15 text-xs text-white cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="retry(job.job_id)"><RotateCcw :size="13" class="inline" /> 重试</button><button type="button" class="min-h-11 px-3 rounded-xl bg-white/10 text-xs text-white cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" :aria-expanded="!!details[job.job_id]" @click="toggleDetails(job.job_id)">附件明细</button></div></div>
      <div class="h-2 rounded-full bg-white/10 overflow-hidden" role="progressbar" :aria-valuenow="job.completed + job.failed + job.canceled" aria-valuemin="0" :aria-valuemax="job.total"><div class="h-full bg-accent" :style="{ width: `${job.total ? (job.completed + job.failed + job.canceled) / job.total * 100 : 0}%` }"></div></div>
      <p class="text-xs text-white/55">完成 {{ job.completed }} / 失败 {{ job.failed }} / 取消 {{ job.canceled }} / 总计 {{ job.total }}</p>
      <ul v-if="details[job.job_id]" class="space-y-2 border-t border-white/10 pt-3"><li v-for="attachment in details[job.job_id]?.attachments || []" :key="attachment.attachment_key" class="flex flex-wrap items-center justify-between gap-2 text-xs text-white/70"><span class="min-w-0 break-all">{{ attachment.filename }} · {{ attachment.status }}<span v-if="attachment.error" class="text-red-300"> · {{ attachment.error }}</span></span><router-link v-if="attachment.media_id" :to="{ path: '/', query: { media: attachment.media_id } }" class="min-h-11 px-3 flex items-center rounded-lg bg-accent/20 text-accent hover:text-white focus-visible:ring-2 focus-visible:ring-accent">打开本地媒体</router-link></li></ul>
    </article>
  </section>
</template>
