<script setup lang="ts">
import axios from 'axios'
import { computed, nextTick, onBeforeUnmount, onDeactivated, onMounted, ref } from 'vue'
import { Loader2, LogOut, UserRound, X } from 'lucide-vue-next'
import { UiButton, UiInput, UiSpinner, fieldHintClass, fieldLabelClass } from '../../ui'
import ExternalSourceLayout from '../ExternalSourceLayout.vue'
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
  <ExternalSourceLayout
    title="Pawchive 账号"
    :status="accountLoading ? '' : accountConnected ? '已连接' : '未登录'"
    :status-tone="accountConnected ? 'success' : 'neutral'"
    :meta="accountLoading ? '正在检查登录状态…' : accountConnected ? '账号收藏的作者会显示在作者页' : '登录后可查看账号收藏的作者'"
    :default-open="!accountLoading && !accountConnected"
  >
    <template #config>
      <section aria-label="Pawchive 账号连接" class="space-y-4">
        <p v-if="accountLoading" role="status" class="flex items-center gap-2 text-meta text-subtle"><UiSpinner :size="16" />正在检查 Pawchive 登录状态…</p>
        <template v-else-if="accountConnected">
          <p class="text-meta text-muted">已连接 Pawchive 账号。会话保存在本机数据库，HE Manager 重启后会自动恢复。</p>
          <UiButton block :loading="accountBusy" @click="logoutAccount">
            <template #icon><LogOut :size="16" aria-hidden="true" /></template>
            {{ accountBusy ? '正在退出…' : '退出 Pawchive' }}
          </UiButton>
        </template>
        <form v-else class="space-y-4" @submit.prevent="loginAccount">
          <label class="block"><span :class="fieldLabelClass">Pawchive 用户名</span><UiInput v-model="accountUsername" autocomplete="username" required maxlength="200" /></label>
          <label class="block"><span :class="fieldLabelClass">Pawchive 密码</span><UiInput v-model="accountPassword" type="password" autocomplete="current-password" required maxlength="1024" /></label>
          <UiButton type="submit" variant="primary" size="lg" block :loading="accountBusy" :disabled="!accountUsername.trim() || !accountPassword">
            <template #icon><UserRound :size="16" aria-hidden="true" /></template>
            {{ accountBusy ? '正在连接…' : '登录 Pawchive' }}
          </UiButton>
        </form>
        <p v-if="accountMessage" role="status" class="text-meta text-success">{{ accountMessage }}</p>
        <p v-if="accountError" role="alert" class="rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">{{ accountError }}</p>
        <p v-if="!accountConnected && !accountLoading" :class="fieldHintClass">HE Manager 只在本机数据库保存 Pawchive 会话，不保存用户名或密码；退出登录会删除会话，会话过期后需要重新登录。</p>
      </section>
    </template>

    <nav aria-label="Pawchive 页面" class="inline-flex items-center gap-0.5 rounded-lg border border-line bg-surface p-0.5">
      <button
        v-for="item in ([{ value: 'browse', label: '作者' }, { value: 'downloads', label: '下载' }] as const)"
        :key="item.value"
        type="button"
        :aria-current="tab === item.value ? 'page' : undefined"
        class="inline-flex h-8 min-w-16 items-center justify-center rounded-md px-3 text-meta font-medium transition-colors duration-150 focus-ring-inset pointer-coarse:h-10"
        :class="tab === item.value ? 'bg-surface-3 text-ink shadow-[0_1px_2px_rgb(0_0_0/0.35)]' : 'text-subtle hover:text-ink'"
        @click="setTab(item.value)"
      >
        {{ item.label }}
      </button>
    </nav>
    <p v-if="downloadMessage && !sequence.active.value" :role="downloadError ? 'alert' : 'status'" class="rounded-lg border px-3.5 py-3 text-meta" :class="downloadError ? 'border-danger/25 bg-danger/10 text-danger' : 'border-success/25 bg-success/10 text-success'">{{ downloadMessage }}</p>
      <PawchiveBrowser v-if="tab === 'browse'" :scope="browse.scope.value" :posts="browse.posts.value" :favorites="accountFavorites" :favorites-loading="accountFavoritesLoading || accountLoading" :account-connected="accountConnected" :favorite-busy-keys="accountFavoriteBusyKeys" :favorite-message="accountError" :status="browse.status.value" :loading-more="browse.loadingMore.value" :has-more="browse.hasMore.value" :error="browse.error.value" :warnings="browse.warnings.value" :capabilities="capabilities" :selected-keys="selectedKeys" :download-busy="downloadBusy" @scope="changeScope" @home="returnToAuthors" @more="browse.loadMore" @open="open" @open-creator="openCreator" @favorite="toggleAccountFavorite" @refresh="refreshAccountFavorites" @select="toggleSelected" @download-selected="downloadSelected" />
      <PawchiveDownloads v-else :refresh-key="refreshKey" />
    <Teleport to="body">
    <PawchiveMediaViewer v-if="sequence.active.value && sequence.current.value" :post="sequence.current.value.post" :attachment="sequence.current.value.attachment" :attachment-index="sequence.current.value.index" :attachment-total="sequence.current.value.total" :attachments="sequence.postAttachments.value" :next-post-key="sequence.nextPost.value?.post_key || null" :next-post-attachments="sequence.nextPostAttachments.value" :scope-label="sequence.scopeLabel.value" :busy="sequence.busy.value" :error="playbackError || sequence.error.value" :notice="sequence.notice.value" :skipped="sequence.skipped.value" :reload-media="sequence.reloadCurrent" :has-previous="sequence.history.value.length > 0" :ended="sequence.ended.value" :autoplay="autoplay" :interval="interval" :download-busy="downloadBusy" :download-message="downloadMessage" :download-error="downloadError" @close="close" @next="advance" @previous="sequence.previous" @select-attachment="selectAttachment" @update:autoplay="autoplay = $event" @update:interval="interval = $event" @playback-error="playbackError = $event" @download-current="downloadCurrent" @download-post="downloadPost" />
    <div v-else-if="sequence.active.value" role="dialog" aria-modal="true" aria-label="正在打开 Pawchive 帖子" class="fixed inset-0 z-[70] flex items-center justify-center bg-black/95 p-6 text-white">
      <div class="max-w-sm space-y-4 text-center">
        <Loader2 v-if="sequence.busy.value" :size="28" class="mx-auto animate-spin text-white/70" />
        <p class="text-body text-white/90">{{ sequence.error.value || (sequence.skipped.value ? `正在查找有媒体的帖子… 已跳过 ${sequence.skipped.value} 篇` : '正在读取帖子…') }}</p>
        <div class="flex justify-center gap-2">
          <button type="button" class="inline-flex h-10 items-center gap-2 rounded-lg px-4 text-body text-white/90 transition-colors hover:bg-white/10 focus-ring pointer-coarse:h-11" @click="close"><X :size="16" aria-hidden="true" />返回列表</button>
          <button v-if="sequence.error.value && !sequence.ended.value" type="button" class="inline-flex h-10 items-center rounded-lg bg-accent px-4 text-body font-medium text-on-accent transition-colors hover:bg-accent/90 focus-ring pointer-coarse:h-11" @click="advance">继续查找</button>
        </div>
      </div>
    </div>
    </Teleport>
  </ExternalSourceLayout>
</template>
