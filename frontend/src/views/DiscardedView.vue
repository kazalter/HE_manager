<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { ArchiveX, RefreshCw } from 'lucide-vue-next'
import { API_BASE_URL } from '../config'
import { authState } from '../auth'
import { EmptyState, PageHeader, UiBadge, UiButton, UiInput, UiModal } from '../components/ui'
import PaginationControl from '../components/PaginationControl.vue'
import { formatBytes, type DiscardRecord } from '../utils/discardApi'
const items = ref<DiscardRecord[]>([]), total = ref(0), page = ref(1), search = ref(''), loading = ref(false), error = ref('')
const allow = ref<DiscardRecord | null>(null), busyId = ref(''), notice = ref('')
let generation = 0, timer: ReturnType<typeof setTimeout> | undefined
const load = async () => {
  const mine = ++generation; loading.value = true; error.value = ''
  try { const { data } = await axios.get<{items: DiscardRecord[]; total: number}>(`${API_BASE_URL}/discard`, { params: { search: search.value, limit: 30, offset: (page.value - 1) * 30 } }); if (mine === generation) { const last = Math.max(1, Math.ceil(data.total / 30)); if (page.value > last) { page.value = last; return }; items.value = data.items; total.value = data.total } }
  catch (err: any) { if (mine === generation) error.value = err.response?.data?.detail || '读取丢弃记录失败' }
  finally { if (mine === generation) loading.value = false }
}
watch(page, () => void load())
watch(search, () => { clearTimeout(timer); timer = setTimeout(() => { if (page.value !== 1) page.value = 1; else void load() }, 300) })
watch(() => authState.token, () => { generation++; items.value = []; allow.value = null })
onBeforeUnmount(() => { generation++; clearTimeout(timer) })
void load()
const action = async (row: DiscardRecord, name: 'retry' | 'allow-download') => {
  busyId.value = row.id; error.value = ''; notice.value = ''
  try {
    const { data } = await axios.post(`${API_BASE_URL}/discard/${row.id}/${name}`, { confirm: true })
    if (name === 'allow-download') { allow.value = null; notice.value = data.message }
    else notice.value = data.cleanup_status === 'completed' ? '本地文件已清理完成' : data.cleanup_error
    await load()
  } catch (err: any) { error.value = err.response?.data?.detail || '操作失败' }
  finally { busyId.value = '' }
}
</script>
<template>
  <div class="min-h-full">
    <PageHeader title="丢弃记录" description="这些内容已从媒体库移除，后续扫描、同步和下载会跳过。">
      <UiButton :loading="loading" @click="load"><template #icon><RefreshCw :size="16" /></template>刷新</UiButton>
    </PageHeader>
    <div class="page-gutter pb-12"><div class="page-container space-y-5">
      <label class="block max-w-lg"><span class="sr-only">搜索丢弃记录</span><UiInput v-model="search" placeholder="搜索丢弃记录…" /></label>
      <p v-if="error" role="alert" class="rounded-xl bg-danger/10 p-3 text-danger">{{ error }}</p>
      <p v-if="notice" role="status" class="rounded-xl bg-surface-2 p-3 text-muted">{{ notice }}</p>
      <EmptyState v-if="!loading && !items.length && !error" :icon="ArchiveX" title="没有丢弃记录" description="删除内容后，会在这里保留来源与处理状态。" />
      <p v-if="loading && !items.length" role="status" class="py-6 text-muted">正在读取…</p>
      <ul v-if="items.length" class="space-y-3">
        <li v-for="row in items" :key="row.id" class="rounded-2xl border border-line bg-surface p-4 sm:p-5">
          <div class="flex flex-wrap items-start justify-between gap-3">
            <div class="min-w-0 flex-1"><p class="break-words text-body font-medium text-ink">{{ row.title }}</p><p class="mt-2 text-caption text-subtle">{{ row.source_type.toUpperCase() }} · {{ row.media_count }} 项 · {{ formatBytes(row.file_size) }} · {{ new Date(row.discarded_at + 'Z').toLocaleString() }}</p></div>
            <UiBadge tone="neutral">丢弃</UiBadge>
          </div>
          <p class="mt-3 text-meta" :class="row.cleanup_status === 'completed' ? 'text-subtle' : 'text-warning'">{{ row.cleanup_status === 'completed' ? '本地文件已删除，来源记录已保留' : row.cleanup_error || '文件清理待完成；后续下载已阻止' }}</p>
          <div class="mt-3 flex flex-wrap gap-2"><UiButton v-if="row.cleanup_status !== 'completed'" :loading="busyId === row.id" @click="action(row, 'retry')">重试清理</UiButton><UiButton v-else variant="ghost" @click="allow = row">允许重新下载</UiButton></div>
        </li>
      </ul>
      <PaginationControl v-if="total > 30" :page="page" :page-count="Math.ceil(total / 30)" :total-items="total" :page-size="30" :disabled="loading" item-label="条记录" @change="page = $event" />
    </div></div>
    <UiModal :hide-close="!!busyId" :close-on-backdrop="!busyId" :open="!!allow" @update:open="!$event && !busyId && (allow = null)" title="允许重新下载" description="取消这条内容的丢弃标记。">
      <p v-if="error" role="alert" class="mb-3 text-meta text-danger">{{ error }}</p>
      <p class="break-words text-body text-ink">{{ allow?.title }}</p><p class="mt-3 text-meta text-subtle">已删除的文件不会恢复。下一次同步或手动下载可以重新获取此内容。</p>
      <template #footer><UiButton :disabled="!!busyId" @click="allow = null">取消</UiButton><UiButton variant="primary" :loading="!!busyId" @click="allow && action(allow, 'allow-download')">允许重新下载</UiButton></template>
    </UiModal>
  </div>
</template>
