<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { Download, ExternalLink, X } from 'lucide-vue-next'
import { RouterLink } from 'vue-router'
import { EmptyState, PageHeader, SectionHeader, UiBadge, UiButton, UiCard, type Tone } from '../components/ui'
import { externalDownloadStore } from '../stores/externalDownloadStore'
import { asmrDownloadStore } from '../stores/asmrDownloadStore'
import PawchiveDownloads from '../components/external/pawchive/PawchiveDownloads.vue'
const actionError = ref('')
const jobs = computed(() => [
  { source: 'WNACG', key: 'wnacg', store: externalDownloadStore },
  { source: 'ASMR', key: 'asmr', store: asmrDownloadStore },
].filter(item => item.store.state.job))
const status: Record<string, string> = { preparing: '准备中', running: '下载中', completed: '已完成', failed: '失败', canceled: '已取消', canceling: '取消中' }
const statusTone: Record<string, Tone> = { preparing: 'info', running: 'info', completed: 'success', failed: 'danger', canceled: 'neutral', canceling: 'warning' }
onMounted(() => { externalDownloadStore.ensureResumed(); asmrDownloadStore.ensureResumed() })
const cancel = async (store: typeof externalDownloadStore | typeof asmrDownloadStore) => {
  actionError.value = ''
  try { await store.cancelDownload() } catch { actionError.value = '取消失败，请稍后重试。' }
}
</script>
<template>
  <div class="min-h-full">
    <PageHeader title="下载任务" description="文件下载到服务器媒体库。离开页面后，服务器会继续执行。" />

    <div class="page-gutter pb-12">
      <div class="page-container">
        <div class="max-w-[960px] space-y-10">
          <section>
            <SectionHeader title="WNACG 与 ASMR" :count="jobs.length ? `${jobs.length} 个任务` : undefined" />
            <p v-if="actionError" role="alert" class="mb-3 flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">{{ actionError }}</p>
            <div v-if="jobs.length" class="space-y-3">
              <UiCard v-for="item in jobs" :key="item.key" as="article" padding="md">
                <div class="flex items-start gap-3">
                  <div class="min-w-0 flex-1">
                    <div class="flex min-w-0 items-center gap-2">
                      <h3 class="shrink-0 text-body font-semibold text-ink">{{ item.source }}</h3>
                      <UiBadge :tone="statusTone[item.store.state.job!.status] || 'neutral'">{{ status[item.store.state.job!.status] || item.store.state.job!.status }}</UiBadge>
                    </div>
                    <p class="mt-1 truncate text-meta text-subtle" :title="item.store.state.job!.current_book_title || undefined">{{ item.store.state.job!.current_book_title || '服务器下载任务' }}</p>
                  </div>
                  <span class="shrink-0 text-heading font-semibold text-ink tabular-nums">{{ item.store.progressPercent.value }}%</span>
                </div>
                <div role="progressbar" :aria-label="item.source + ' 下载进度'" :aria-valuenow="item.store.progressPercent.value" aria-valuemin="0" aria-valuemax="100" class="mt-3 h-1 overflow-hidden rounded-sm bg-surface-3"><div class="h-full rounded-sm bg-accent" :style="{ width: item.store.progressPercent.value + '%' }"></div></div>
                <p v-if="item.store.state.errorMessage" role="alert" class="mt-3 flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">{{ item.store.state.errorMessage }}</p>
                <div class="mt-3 flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
                  <p class="text-meta text-subtle tabular-nums">完成 {{ item.store.state.job!.completed }} / {{ item.store.state.job!.total }} · <span :class="item.store.state.job!.failed ? 'text-danger' : ''">失败 {{ item.store.state.job!.failed }}</span></p>
                  <div class="ml-auto flex items-center gap-2">
                    <UiButton v-if="item.store.canCancel.value" variant="ghost" size="sm" class="pointer-coarse:h-10" @click="cancel(item.store)">
                      <template #icon><X :size="14" /></template>取消下载
                    </UiButton>
                    <UiButton :as="RouterLink" :to="{ path: '/external', query: { source: item.key } }" variant="secondary" size="sm" class="pointer-coarse:h-10">
                      <template #icon><ExternalLink :size="14" /></template>详情与重试
                    </UiButton>
                  </div>
                </div>
              </UiCard>
            </div>
            <UiCard v-else padding="none">
              <EmptyState compact :icon="Download" title="暂无下载任务" description="可从「发现」提交 WNACG 或 ASMR 下载。" />
            </UiCard>
          </section>

          <div class="he-downloads-pawchive"><PawchiveDownloads :refresh-key="0" /></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* PawchiveDownloads is restyled by the external-page work; keep its buttons from wrapping per character here. */
.he-downloads-pawchive :deep(button) { white-space: nowrap; flex-shrink: 0; }
</style>
