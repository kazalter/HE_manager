<script setup lang="ts">
import axios from 'axios'
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import { Loader2, LogOut, UserRound, X } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import PawchiveBrowser from './PawchiveBrowser.vue'
import PawchiveDownloads from './PawchiveDownloads.vue'
import PawchiveMediaViewer from './PawchiveMediaViewer.vue'
import { usePawchiveBrowse } from '../../../composables/usePawchiveBrowse'
import { usePawchiveSequence } from '../../../composables/usePawchiveSequence'
import type { PawchiveCapabilities, PawchiveCreator, PawchiveCreatorFavorite, PawchiveDownloadSelection, PawchivePost, PawchiveScope } from '../../../types/pawchive'
import {
  createPawchiveDownload,
  fetchPawchiveAccountFavorites,
  fetchPawchiveAccountStatus,
  fetchPawchiveCapabilities,
  loginPawchiveAccount,
  logoutPawchiveAccount,
  pawchiveError,
  previewPawchiveDownload,
  removePawchiveAccountFavorite,
  setPawchiveAccountFavorite,
} from '../../../utils/pawchiveApi'

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
const accountConnected = ref(false)
const accountLoading = ref(true)
const accountBusy = ref(false)
const accountFavoritesLoading = ref(false)
const accountUsername = ref('')
const accountPassword = ref('')
const accountFavorites = ref<PawchiveCreatorFavorite[]>([])
const accountFavoriteBusyKeys = ref<string[]>([])
const accountError = ref('')
const accountMessage = ref('')
const lastAuthorQuery = ref('')
let opener: HTMLElement | null = null

function favoriteCreatorKey(creator: Pick<PawchiveCreatorFavorite, 'service' | 'creator_id'>) {
  return `${creator.service}:${creator.creator_id}`
}

const refreshAccountFavorites = async () => {
  accountFavoritesLoading.value = true
  try {
    accountFavorites.value = await fetchPawchiveAccountFavorites()
    accountError.value = ''
    return true
  } catch (cause) {
    accountError.value = pawchiveError(cause)
    if (axios.isAxiosError(cause) && cause.response?.status === 401) {
      accountConnected.value = false
      accountFavorites.value = []
    }
    return false
  } finally {
    accountFavoritesLoading.value = false
  }
}

const refreshAccountStatus = async () => {
  accountLoading.value = true
  accountError.value = ''
  try {
    const status = await fetchPawchiveAccountStatus()
    accountConnected.value = status.connected
    if (status.connected) await refreshAccountFavorites()
    else accountFavorites.value = []
  } catch (cause) {
    accountConnected.value = false
    accountFavorites.value = []
    accountError.value = pawchiveError(cause)
  } finally {
    accountLoading.value = false
  }
}

const loginAccount = async () => {
  if (accountBusy.value) return
  accountBusy.value = true
  accountError.value = ''
  accountMessage.value = ''
  try {
    const result = await loginPawchiveAccount(accountUsername.value.trim(), accountPassword.value)
    accountConnected.value = result.connected
    accountFavorites.value = result.items || []
    accountPassword.value = ''
    accountMessage.value = '已连接 Pawchive 账号。会话状态会在 HE Manager 重启后恢复。'
  } catch (cause) {
    accountError.value = pawchiveError(cause) || 'Pawchive 登录失败，请检查账号信息。'
  } finally {
    accountBusy.value = false
  }
}

const logoutAccount = async () => {
  if (accountBusy.value) return
  accountBusy.value = true
  accountError.value = ''
  accountMessage.value = ''
  try {
    await logoutPawchiveAccount()
    accountConnected.value = false
    accountFavorites.value = []
    accountPassword.value = ''
    accountMessage.value = '已退出 Pawchive 账号。'
  } catch (cause) {
    accountError.value = pawchiveError(cause)
  } finally {
    accountBusy.value = false
  }
}

const toggleAccountFavorite = async (post: Pick<PawchiveCreatorFavorite, 'service' | 'creator_id' | 'creator_name' | 'source_url'>) => {
  if (!accountConnected.value) {
    accountError.value = '请先登录 Pawchive 账号。'
    return
  }
  const creator = { service: post.service, creator_id: post.creator_id }
  const key = favoriteCreatorKey(creator)
  if (accountFavoriteBusyKeys.value.includes(key)) return
  accountFavoriteBusyKeys.value = [...accountFavoriteBusyKeys.value, key]
  accountError.value = ''
  accountMessage.value = ''
  try {
    const exists = accountFavorites.value.some(item => favoriteCreatorKey(item) === key)
    if (exists) {
      await removePawchiveAccountFavorite(creator)
      accountFavorites.value = accountFavorites.value.filter(item => favoriteCreatorKey(item) !== key)
      accountMessage.value = `已取消收藏作者 ${post.creator_name}。`
    } else {
      await setPawchiveAccountFavorite(creator)
      accountFavorites.value = [...accountFavorites.value, {
        ...creator,
        creator_name: post.creator_name,
        source_url: post.source_url,
      }]
      await refreshAccountFavorites()
      accountMessage.value = `已收藏作者 ${post.creator_name}。`
    }
  } catch (cause) {
    accountError.value = pawchiveError(cause)
  } finally {
    accountFavoriteBusyKeys.value = accountFavoriteBusyKeys.value.filter(item => item !== key)
  }
}

const changeScope = (scope: PawchiveScope) => {
  sequence.close()
  selectedKeys.value = []
  if (scope.creatorId) {
    void browse.setScope(scope)
  } else if (scope.query.trim()) {
    lastAuthorQuery.value = scope.query.trim()
    void browse.setScope(scope)
  } else {
    lastAuthorQuery.value = ''
    browse.resetScope()
  }
}
const returnToAuthors = (fromCreator: boolean) => changeScope({
  query: fromCreator ? lastAuthorQuery.value : '', service: '', creatorId: '', tag: '', mediaType: 'all',
})
const openCreator = (creator: PawchiveCreator) => changeScope({
  query: '', service: creator.service, creatorId: creator.creator_id, tag: '', mediaType: 'all',
})
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
const selectAttachment = (index: number) => {
  playbackError.value = ''
  sequence.selectAttachment(index)
}
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
  void refreshAccountStatus()
})
onDeactivated(() => { sequence.close(); autoplay.value = false })
onBeforeUnmount(() => { browse.dispose(); sequence.close() })
</script>

<template>
  <section class="relative z-10 space-y-5">
      <nav aria-label="Pawchive 页面" class="flex gap-2 border-b border-white/10 pb-3">
        <button type="button" :aria-current="tab === 'browse' ? 'page' : undefined" :class="tab === 'browse' ? 'bg-accent text-white' : 'bg-white/5 text-white/70'" class="min-h-11 px-5 rounded-xl text-sm font-bold cursor-pointer focus-visible:ring-2 focus-visible:ring-white" @click="setTab('browse')">作者</button>
        <button type="button" :aria-current="tab === 'downloads' ? 'page' : undefined" :class="tab === 'downloads' ? 'bg-accent text-white' : 'bg-white/5 text-white/70'" class="min-h-11 px-5 rounded-xl text-sm font-bold cursor-pointer focus-visible:ring-2 focus-visible:ring-white" @click="setTab('downloads')">下载</button>
      </nav>
      <p v-if="downloadMessage && !sequence.active.value" :role="downloadError ? 'alert' : 'status'" :class="downloadError ? 'text-red-300' : 'text-emerald-300'" class="text-sm">{{ downloadMessage }}</p>
      <section v-if="tab === 'browse'" aria-label="Pawchive 账号连接" class="rounded-2xl border border-white/10 bg-white/[0.035] p-4">
        <div class="flex flex-wrap items-center justify-between gap-3 mb-4">
          <div class="flex items-center gap-2 text-white"><UserRound :size="18" class="text-accent" aria-hidden="true" /><h2 class="text-base font-bold">Pawchive 账号连接</h2></div>
          <button v-if="accountConnected" type="button" :disabled="accountBusy" class="min-h-10 px-4 inline-flex items-center gap-2 rounded-xl border border-white/15 text-sm text-white/75 disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="logoutAccount">
            <LogOut :size="15" aria-hidden="true" />{{ accountBusy ? '正在退出…' : '退出 Pawchive' }}
          </button>
        </div>
        <p v-if="accountLoading" role="status" class="flex items-center gap-2 text-sm text-white/60"><Loader2 :size="16" class="animate-spin" aria-hidden="true" />正在检查 Pawchive 登录状态…</p>
        <p v-else-if="accountConnected" class="text-sm text-emerald-200">已连接 Pawchive 账号。账号收藏作者会显示在下方。</p>
        <form v-else class="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end" @submit.prevent="loginAccount">
          <label class="min-w-0"><span class="block text-xs font-semibold text-white/65 mb-2">Pawchive 用户名</span><input v-model="accountUsername" autocomplete="username" required maxlength="200" class="w-full min-h-11 rounded-xl border border-white/15 bg-black/20 px-3 text-sm text-white" /></label>
          <label class="min-w-0"><span class="block text-xs font-semibold text-white/65 mb-2">Pawchive 密码</span><input v-model="accountPassword" type="password" autocomplete="current-password" required maxlength="1024" class="w-full min-h-11 rounded-xl border border-white/15 bg-black/20 px-3 text-sm text-white" /></label>
          <button type="submit" :disabled="accountBusy || !accountUsername.trim() || !accountPassword" class="min-h-11 px-5 inline-flex items-center justify-center gap-2 rounded-xl bg-accent text-sm font-bold text-white disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-white">
            <Loader2 v-if="accountBusy" :size="15" class="animate-spin" aria-hidden="true" /><UserRound v-else :size="15" aria-hidden="true" />{{ accountBusy ? '正在连接…' : '登录 Pawchive' }}
          </button>
        </form>
        <p v-if="accountMessage" role="status" class="mt-3 text-sm text-emerald-200">{{ accountMessage }}</p>
        <p v-if="accountError" role="alert" class="mt-3 text-sm text-red-200">{{ accountError }}</p>
        <p v-if="!accountConnected && !accountLoading" class="mt-3 text-xs text-white/45">登录后可查看账号收藏的作者。HE Manager 仅在本机数据库保存 Pawchive 会话，不保存用户名或密码；退出登录会删除会话。会话过期后需要重新登录。</p>
      </section>
      <PawchiveBrowser v-if="tab === 'browse'" :scope="browse.scope.value" :posts="browse.posts.value" :favorites="accountFavorites" :favorites-loading="accountFavoritesLoading || accountLoading" :account-connected="accountConnected" :favorite-busy-keys="accountFavoriteBusyKeys" :favorite-message="accountError" :status="browse.status.value" :loading-more="browse.loadingMore.value" :has-more="browse.hasMore.value" :error="browse.error.value" :warnings="browse.warnings.value" :capabilities="capabilities" :selected-keys="selectedKeys" :download-busy="downloadBusy" @scope="changeScope" @home="returnToAuthors" @more="browse.loadMore" @open="open" @open-creator="openCreator" @favorite="toggleAccountFavorite" @refresh="refreshAccountFavorites" @select="toggleSelected" @download-selected="downloadSelected" />
      <PawchiveDownloads v-else :refresh-key="refreshKey" />
    <Teleport to="body">
    <PawchiveMediaViewer v-if="sequence.active.value && sequence.current.value" :post="sequence.current.value.post" :attachment="sequence.current.value.attachment" :attachment-index="sequence.current.value.index" :attachment-total="sequence.current.value.total" :attachments="sequence.postAttachments.value" :next-post-key="sequence.nextPost.value?.post_key || null" :next-post-attachments="sequence.nextPostAttachments.value" :scope-label="sequence.scopeLabel.value" :busy="sequence.busy.value" :error="playbackError || sequence.error.value || sequence.notice.value" :has-previous="sequence.history.value.length > 0" :ended="sequence.ended.value" :autoplay="autoplay" :interval="interval" :download-busy="downloadBusy" :download-message="downloadMessage" :download-error="downloadError" @close="close" @next="advance" @previous="sequence.previous" @select-attachment="selectAttachment" @update:autoplay="autoplay = $event" @update:interval="interval = $event" @playback-error="playbackError = $event" @download-current="downloadCurrent" @download-post="downloadPost" />
    <div v-else-if="sequence.active.value" role="dialog" aria-modal="true" aria-label="正在打开 Pawchive 帖子" class="fixed inset-0 z-[70] bg-black/95 text-white flex items-center justify-center p-6">
      <div class="text-center space-y-4"><Loader2 v-if="sequence.busy.value" :size="28" class="animate-spin mx-auto text-accent" /><p>{{ sequence.error.value || '正在读取帖子…' }}</p><div class="flex justify-center gap-3"><button type="button" class="min-h-11 px-4 rounded-xl border border-white/20" @click="close"><X :size="16" class="inline" /> 返回列表</button><button v-if="sequence.error.value" type="button" class="min-h-11 px-4 rounded-xl bg-accent" @click="advance">继续查找</button></div></div>
    </div>
    </Teleport>
  </section>
</template>
