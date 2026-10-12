<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { Trash2 } from 'lucide-vue-next'
import { API_BASE_URL } from '../../config'
import type { XPost } from '../../types'
import { UiBadge, UiButton, UiCard } from '../ui'
import PaginationControl from '../PaginationControl.vue'
import DiscardContentDialog from '../DiscardContentDialog.vue'
import type { DiscardRecord, DiscardTarget } from '../../utils/discardApi'
const props = defineProps<{ sourceId: number }>()
const emit = defineEmits<{ changed: [] }>()
const posts = ref<XPost[]>([]), total = ref(0), page = ref(1), status = ref(''), loading = ref(false), error = ref('')
const target = ref<DiscardTarget | null>(null), notice = ref('')
let generation = 0
const pages = computed(() => Math.max(1, Math.ceil(total.value / 20)))
const labels: Record<string, string> = { pending: '待导入', fetched: '已获取', downloading: '下载中', completed: '已导入', failed: '失败', skipped: '跳过', discarded: '丢弃' }
const load = async () => {
  const mine = ++generation; loading.value = true; error.value = ''
  try { const response = await axios.get<XPost[]>(`${API_BASE_URL}/x/sources/${props.sourceId}/posts`, { params: { status: status.value || undefined, limit: 20, offset: (page.value - 1) * 20 } }); if (mine === generation) { const count = Number(response.headers['x-total-count']) || 0; const last = Math.max(1, Math.ceil(count / 20)); if (page.value > last) { page.value = last; return }; posts.value = response.data; total.value = count } }
  catch (err: any) { if (mine === generation) error.value = err.response?.data?.detail || '读取帖子失败' }
  finally { if (mine === generation) loading.value = false }
}
watch(() => props.sourceId, () => { page.value = 1; void load() }, { immediate: true })
watch(page, () => void load())
watch(status, () => { if (page.value !== 1) page.value = 1; else void load() })
onBeforeUnmount(() => { generation++ })
const changed = async (record: DiscardRecord) => { notice.value = record.cleanup_error || '已丢弃整条帖子，下次导入会跳过。'; await load(); emit('changed') }
</script>
<template>
  <UiCard padding="none">
    <div class="flex flex-wrap items-center justify-between gap-3 p-4"><h3 class="text-body font-semibold text-ink">收藏与导入记录</h3><div class="flex items-center gap-2"><label class="sr-only" for="x-post-state">帖子状态</label><select id="x-post-state" v-model="status" class="min-h-11 rounded-xl border border-line bg-surface-2 px-3 text-meta text-ink focus-ring"><option value="">全部状态</option><option v-for="(label, key) in labels" :key="key" :value="key">{{ label }}</option></select><UiButton :loading="loading" @click="load">刷新</UiButton></div></div>
    <p v-if="error" role="alert" class="px-4 pb-3 text-danger">{{ error }}</p><p v-if="notice" role="status" class="px-4 pb-3 text-meta text-muted">{{ notice }} <router-link to="/discarded" class="text-accent underline">丢弃记录</router-link></p>
    <p v-if="!loading && !posts.length" class="p-4 text-meta text-subtle">没有符合条件的记录</p>
    <ul class="divide-y divide-line"><li v-for="post in posts" :key="post.id" class="flex items-center gap-3 p-4"><div class="min-w-0 flex-1"><a :href="post.url" target="_blank" rel="noreferrer" class="line-clamp-2 break-words text-meta font-medium text-ink hover:text-accent">{{ post.full_text || `@${post.author_screen_name || 'x'} · ${post.tweet_id}` }}</a><p class="mt-1 text-caption text-subtle">{{ post.tweet_id }} · {{ post.media_count }} 个附件</p></div><UiBadge :tone="post.status === 'discarded' ? 'neutral' : 'info'">{{ labels[post.status] || post.status }}</UiBadge><button v-if="post.status !== 'discarded'" type="button" class="grid size-11 shrink-0 place-items-center rounded-xl text-subtle hover:bg-danger/10 hover:text-danger focus-ring" :aria-label="`删除并丢弃 X 帖子 ${post.tweet_id}`" title="丢弃整条帖子" @click="target = { kind: 'x_post', target_id: post.id }"><Trash2 :size="17" /></button></li></ul>
    <div v-if="pages > 1" class="p-4"><PaginationControl :page="page" :page-count="pages" :total-items="total" :page-size="20" :disabled="loading" item-label="条帖子" @change="page = $event" /></div>
  </UiCard>
  <DiscardContentDialog v-model:target="target" @discarded="changed" />
</template>
