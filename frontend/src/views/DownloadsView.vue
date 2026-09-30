<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download } from 'lucide-vue-next'
import { externalDownloadStore } from '../stores/externalDownloadStore'
import { asmrDownloadStore } from '../stores/asmrDownloadStore'
import PawchiveDownloads from '../components/external/pawchive/PawchiveDownloads.vue'
const actionError = ref('')
const jobs = computed(() => [
  { source: 'WNACG', key: 'wnacg', store: externalDownloadStore },
  { source: 'ASMR', key: 'asmr', store: asmrDownloadStore },
].filter(item => item.store.state.job))
const status: Record<string, string> = { preparing: '准备中', running: '下载中', completed: '已完成', failed: '失败', canceled: '已取消', canceling: '取消中' }
onMounted(() => { externalDownloadStore.ensureResumed(); asmrDownloadStore.ensureResumed() })
const cancel = async (store: typeof externalDownloadStore | typeof asmrDownloadStore) => {
  actionError.value = ''
  try { await store.cancelDownload() } catch { actionError.value = '取消失败，请稍后重试。' }
}
</script>
<template>
  <div class="p-4 sm:p-8 max-w-4xl mx-auto space-y-6">
    <header class="he-page-header"><h1 class="text-2xl font-bold flex items-center gap-3"><Download :size="24" aria-hidden="true" />下载任务</h1><p class="text-sm text-white/65 mt-2">文件下载到服务器媒体库。离开页面后，服务器会继续执行。</p></header>
    <p v-if="actionError" role="alert" class="text-red-300">{{ actionError }}</p>
    <article v-for="item in jobs" :key="item.key" class="p-4 rounded-2xl border border-white/10 bg-white/[0.04] space-y-3">
      <div class="flex justify-between gap-3"><h2 class="font-bold">{{ item.source }} · {{ status[item.store.state.job!.status] || item.store.state.job!.status }}</h2><span class="text-sm text-white/70">{{ item.store.progressPercent.value }}%</span></div>
      <p class="text-sm text-white/70 break-words">{{ item.store.state.job!.current_book_title || '服务器下载任务' }}</p>
      <div role="progressbar" :aria-label="item.source + ' 下载进度'" :aria-valuenow="item.store.progressPercent.value" aria-valuemin="0" aria-valuemax="100" class="h-2 bg-white/10 rounded-full overflow-hidden"><div class="h-full bg-accent" :style="{ width: item.store.progressPercent.value + '%' }"></div></div>
      <p class="text-xs text-white/65">完成 {{ item.store.state.job!.completed }} / {{ item.store.state.job!.total }} · 失败 {{ item.store.state.job!.failed }}</p>
      <p v-if="item.store.state.errorMessage" role="alert" class="text-sm text-red-300">{{ item.store.state.errorMessage }}</p>
      <div class="flex gap-3"><router-link :to="{ path: '/external', query: { source: item.key } }" class="min-h-11 px-4 rounded-xl bg-accent/20 text-accent inline-flex items-center">详情与重试</router-link><button v-if="item.store.canCancel.value" type="button" class="min-h-11 px-4 rounded-xl border border-white/15" @click="cancel(item.store)">取消下载</button></div>
    </article>
    <p v-if="!jobs.length" class="text-sm text-white/65">暂无 WNACG 或 ASMR 下载任务。可从「发现」提交下载。</p>
    <PawchiveDownloads :refresh-key="0" />
  </div>
</template>
