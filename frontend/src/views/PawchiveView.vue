<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref } from 'vue'
import { Globe2, Loader2, X } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import PawchiveBrowser from '../components/external/pawchive/PawchiveBrowser.vue'
import PawchiveDownloads from '../components/external/pawchive/PawchiveDownloads.vue'
import PawchiveMediaViewer from '../components/external/pawchive/PawchiveMediaViewer.vue'
import { usePawchiveBrowse } from '../composables/usePawchiveBrowse'
import { usePawchiveSequence } from '../composables/usePawchiveSequence'
import type { PawchiveCapabilities, PawchiveDownloadSelection, PawchivePost, PawchiveScope } from '../types/pawchive'
import { createPawchiveDownload, fetchPawchiveCapabilities, pawchiveError, previewPawchiveDownload } from '../utils/pawchiveApi'

const route = useRoute()
const router = useRouter()
const tab = computed(() => route.query.tab === 'downloads' ? 'downloads' : 'browse')
const setTab = (value: 'browse' | 'downloads') => { void router.replace({ path: route.path, query: { ...route.query, tab: value } }) }
const browse = usePawchiveBrowse()
const sequence = usePawchiveSequence()
const autoplay = ref(false)
const interval = ref(5)
const capabilities = ref<PawchiveCapabilities | null>(null)
const playbackError = ref('')
const selectedKeys = ref<string[]>([])
const downloadBusy = ref(false)
const downloadMessage = ref('')
const downloadError = ref(false)
const refreshKey = ref(0)
let opener: HTMLElement | null = null
const changeScope = (scope: PawchiveScope) => {
  sequence.close()
  selectedKeys.value = []
  void browse.setScope(scope)
}
const toggleSelected = (post: PawchivePost) => {
  selectedKeys.value = selectedKeys.value.includes(post.post_key)
    ? selectedKeys.value.filter(key => key !== post.post_key)
    : [...selectedKeys.value, post.post_key].slice(0, 20)
}
const open = (index: number) => {
  opener = document.activeElement as HTMLElement | null
  playbackError.value = ''
  downloadMessage.value = ''
  downloadError.value = false
  void sequence.open(index, browse.posts.value, browse.nextCursor.value, browse.hasMore.value, browse.scope.value)
}
const close = async () => {
  sequence.close()
  autoplay.value = false
  await nextTick()
  opener?.focus()
}
const advance = () => { playbackError.value = ''; void sequence.next() }
const submitDownload = async (selections: PawchiveDownloadSelection[], goToDownloads = false) => {
  if (!selections.length || downloadBusy.value) return
  downloadBusy.value = true
  downloadMessage.value = ''
  downloadError.value = false
  try {
    const preview = await previewPawchiveDownload(selections)
    if (!preview.supported) { downloadMessage.value = '所选内容没有受支持的图片或视频。'; return }
    if (preview.supported === preview.already_downloaded) { downloadMessage.value = '所选附件已全部入库。'; return }
    const confirmed = window.confirm(`即将提交 ${preview.selected_posts} 篇帖子中的 ${preview.supported - preview.already_downloaded} 个附件。\n已入库 ${preview.already_downloaded} 个，不支持 ${preview.unsupported} 个；文件大小未知。\n确认下载吗？`)
    if (!confirmed) return
    const created = await createPawchiveDownload(selections)
    downloadMessage.value = created.queued ? `已加入队列：${created.queued} 个附件。` : '所选附件已在下载或已入库。'
    refreshKey.value++
    if (goToDownloads) { selectedKeys.value = []; setTab('downloads') }
  } catch (cause) {
    downloadError.value = true
    downloadMessage.value = pawchiveError(cause)
  } finally { downloadBusy.value = false }
}
const downloadSelected = () => {
  const selections = browse.posts.value.filter(post => selectedKeys.value.includes(post.post_key)).map(post => ({
    service: post.service, creator_id: post.creator_id, post_id: post.post_id,
  }))
  void submitDownload(selections, true)
}
const downloadCurrent = () => {
  const item = sequence.current.value
  if (!item) return
  void submitDownload([{ service: item.post.service, creator_id: item.post.creator_id,
    post_id: item.post.post_id, attachment_keys: [item.attachment.attachment_key] }])
}
const downloadPost = () => {
  const item = sequence.current.value
  if (!item) return
  void submitDownload([{ service: item.post.service, creator_id: item.post.creator_id, post_id: item.post.post_id }])
}
onMounted(() => {
  void fetchPawchiveCapabilities().then(value => { capabilities.value = value }).catch(() => { capabilities.value = null })
  void browse.setScope(browse.scope.value)
})
onBeforeUnmount(() => { browse.dispose(); sequence.close() })
</script>

<template>
  <div class="min-h-screen relative z-10">
    <header class="he-page-header sticky top-0 z-30 bg-background/80 backdrop-blur-xl border-b border-white/10 px-6 md:px-8 py-5 mb-6">
      <div class="flex items-center gap-3">
        <div class="w-10 h-10 rounded-xl bg-accent/15 text-accent flex items-center justify-center"><Globe2 :size="20" aria-hidden="true" /></div>
        <div><h1 class="text-2xl md:text-3xl font-black text-white">Pawchive</h1><p class="text-xs text-white/50">外部源 · 在线浏览</p></div>
      </div>
    </header>
    <main class="px-4 sm:px-6 md:px-8 pb-12">
      <nav aria-label="Pawchive 页面" class="flex gap-2 mb-5 border-b border-white/10 pb-3">
        <button type="button" :aria-current="tab === 'browse' ? 'page' : undefined" :class="tab === 'browse' ? 'bg-accent text-white' : 'bg-white/5 text-white/70'" class="min-h-11 px-5 rounded-xl text-sm font-bold cursor-pointer focus-visible:ring-2 focus-visible:ring-white" @click="setTab('browse')">浏览</button>
        <button type="button" :aria-current="tab === 'downloads' ? 'page' : undefined" :class="tab === 'downloads' ? 'bg-accent text-white' : 'bg-white/5 text-white/70'" class="min-h-11 px-5 rounded-xl text-sm font-bold cursor-pointer focus-visible:ring-2 focus-visible:ring-white" @click="setTab('downloads')">下载</button>
      </nav>
      <p v-if="downloadMessage && !sequence.active.value" :role="downloadError ? 'alert' : 'status'" :class="downloadError ? 'text-red-300' : 'text-emerald-300'" class="text-sm mb-4">{{ downloadMessage }}</p>
      <PawchiveBrowser v-if="tab === 'browse'" :scope="browse.scope.value" :posts="browse.posts.value" :status="browse.status.value" :loading-more="browse.loadingMore.value" :has-more="browse.hasMore.value" :error="browse.error.value" :warnings="browse.warnings.value" :capabilities="capabilities" :selected-keys="selectedKeys" :download-busy="downloadBusy" @scope="changeScope" @more="browse.loadMore" @open="open" @select="toggleSelected" @download-selected="downloadSelected" />
      <PawchiveDownloads v-else :refresh-key="refreshKey" />
    </main>
    <Teleport to="body">
    <PawchiveMediaViewer v-if="sequence.active.value && sequence.current.value" :post="sequence.current.value.post" :attachment="sequence.current.value.attachment" :attachment-index="sequence.current.value.index" :attachment-total="sequence.current.value.total" :scope-label="sequence.scopeLabel.value" :busy="sequence.busy.value" :error="playbackError || sequence.error.value || sequence.notice.value" :has-previous="sequence.history.value.length > 0" :ended="sequence.ended.value" :autoplay="autoplay" :interval="interval" :download-busy="downloadBusy" :download-message="downloadMessage" :download-error="downloadError" @close="close" @next="advance" @previous="sequence.previous" @update:autoplay="autoplay = $event" @update:interval="interval = $event" @playback-error="playbackError = $event" @download-current="downloadCurrent" @download-post="downloadPost" />
    <div v-else-if="sequence.active.value" role="dialog" aria-modal="true" aria-label="正在打开 Pawchive 帖子" class="fixed inset-0 z-[70] bg-black/95 text-white flex items-center justify-center p-6">
      <div class="text-center space-y-4"><Loader2 v-if="sequence.busy.value" :size="28" class="animate-spin mx-auto text-accent" /><p>{{ sequence.error.value || '正在读取帖子…' }}</p><div class="flex justify-center gap-3"><button type="button" class="min-h-11 px-4 rounded-xl border border-white/20" @click="close"><X :size="16" class="inline" /> 返回列表</button><button v-if="sequence.error.value" type="button" class="min-h-11 px-4 rounded-xl bg-accent" @click="advance">继续查找</button></div></div>
    </div>
    </Teleport>
  </div>
</template>
