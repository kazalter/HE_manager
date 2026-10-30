<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import { ArrowLeft, Gamepad2, LoaderCircle, Play, Square } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { API_BASE_URL } from '../config'
import { authState } from '../auth'
import type { Media } from '../types'
import { PageHeader, UiButton } from '../components/ui'

interface GameSession {
  active: boolean
  configured?: boolean
  recoverable?: boolean
  id?: string
  media_id?: number
  title?: string
  launcher?: string
}

const route = useRoute()
const router = useRouter()
const media = ref<Media | null>(null)
const launchers = ref<string[]>([])
const selectedLauncher = ref('')
const session = ref<GameSession>({ active: false })
const loading = ref(true)
const starting = ref(false)
const stopping = ref(false)
const streamLoading = ref(false)
const error = ref('')
const requestId = ref(0)
const mediaId = computed(() => Number(route.params.mediaId))
const isAdmin = computed(() => Boolean(authState.user?.is_admin))
const secureBrowser = typeof window !== 'undefined' && window.isSecureContext
const canStart = computed(() => isAdmin.value && secureBrowser && session.value.configured !== false && !!selectedLauncher.value && !session.value.active)
const streamUrl = computed(() => session.value.active && session.value.id && session.value.media_id === mediaId.value
  ? `${window.location.origin}/games/session/${session.value.id}/`
  : '')

const detailError = (err: any) => {
  if (err?.response?.status === 403) return '只有管理员可以启动游戏。'
  if (err?.response?.status === 401) return '登录状态已失效，请重新登录。'
  return err?.response?.data?.detail || '无法连接游戏运行服务，请稍后重试。'
}

const load = async () => {
  const current = ++requestId.value
  loading.value = true
  error.value = ''
  media.value = null
  launchers.value = []
  selectedLauncher.value = ''
  try {
    const [mediaRes, launchersRes, sessionRes] = await Promise.all([
      axios.get<Media>(`${API_BASE_URL}/media/${mediaId.value}`),
      axios.get<{ launchers: string[]; suggested: string | null }>(`${API_BASE_URL}/games/${mediaId.value}/launchers`),
      axios.get<GameSession>(`${API_BASE_URL}/games/status`),
    ])
    if (current !== requestId.value) return
    if (mediaRes.data.media_type !== 'game') throw new Error('该媒体不是游戏文件夹')
    media.value = mediaRes.data
    launchers.value = launchersRes.data.launchers
    selectedLauncher.value = launchersRes.data.suggested || launchersRes.data.launchers[0] || ''
    session.value = sessionRes.data
  } catch (err: any) {
    if (current === requestId.value) error.value = err.message === '该媒体不是游戏文件夹' ? err.message : detailError(err)
  } finally {
    if (current === requestId.value) loading.value = false
  }
}

const start = async () => {
  if (!canStart.value) return
  starting.value = true
  error.value = ''
  try {
    const res = await axios.post<GameSession>(`${API_BASE_URL}/games/${mediaId.value}/session`, { launcher: selectedLauncher.value })
    session.value = res.data
    streamLoading.value = true
  } catch (err: any) {
    error.value = detailError(err)
    if (err?.response?.status === 409) {
      try { session.value = (await axios.get<GameSession>(`${API_BASE_URL}/games/status`)).data } catch { /* Keep the launch error visible. */ }
    }
  } finally {
    starting.value = false
  }
}

const stop = async () => {
  stopping.value = true
  error.value = ''
  try {
    await axios.post(`${API_BASE_URL}/games/stop`)
    session.value = { active: false, configured: true }
    streamLoading.value = false
  } catch (err: any) {
    error.value = detailError(err)
  } finally {
    stopping.value = false
  }
}

onMounted(load)
watch(mediaId, load)
</script>

<template>
  <div class="min-h-full pb-12">
    <PageHeader :title="media?.title || '游戏'" description="游戏运行在 Linux 主机上，浏览器负责画面和输入。">
      <template #leading>
        <button type="button" class="grid size-10 shrink-0 place-items-center rounded-xl text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-ring" aria-label="返回游戏分类" @click="router.push('/type/game')">
          <ArrowLeft :size="18" aria-hidden="true" />
        </button>
      </template>
      <template #actions>
        <UiButton v-if="session.active" variant="danger" :loading="stopping" @click="stop">
          <template #icon><Square :size="15" aria-hidden="true" /></template>
          停止游戏
        </UiButton>
      </template>
    </PageHeader>

    <div class="page-gutter">
      <div class="page-container space-y-4">
        <p v-if="error" role="alert" class="rounded-xl border border-danger/25 bg-danger/10 px-4 py-3 text-meta text-danger">{{ error }}</p>

        <section class="overflow-hidden rounded-2xl border border-line bg-surface">
          <div class="relative aspect-video min-h-[240px] w-full bg-black sm:min-h-[360px] lg:min-h-[480px]">
            <iframe
              v-if="streamUrl"
              :key="streamUrl"
              :src="streamUrl"
              title="游戏画面"
              class="absolute inset-0 h-full w-full border-0"
              allow="autoplay; fullscreen; gamepad; clipboard-read; clipboard-write"
              allowfullscreen
              @load="streamLoading = false"
            />
            <div v-else class="absolute inset-0 flex flex-col items-center justify-center gap-3 px-6 text-center text-white/75">
              <Gamepad2 :size="36" stroke-width="1.5" aria-hidden="true" />
              <p class="text-meta">{{ loading ? '正在读取游戏信息…' : session.active ? '正在恢复游戏会话…' : '启动后，游戏画面会显示在这里' }}</p>
            </div>
            <div v-if="streamLoading" class="absolute inset-0 flex items-center justify-center bg-black/70 text-white">
              <span class="inline-flex items-center gap-2 text-meta"><LoaderCircle :size="17" class="animate-spin" aria-hidden="true" />正在连接游戏画面…</span>
            </div>
          </div>

          <div class="flex flex-col gap-4 border-t border-line p-4 sm:flex-row sm:items-center sm:justify-between sm:px-5">
            <div class="min-w-0">
              <h2 class="text-body font-semibold text-ink">{{ session.active ? (session.title || media?.title || '游戏会话') : '启动游戏' }}</h2>
              <p v-if="session.active" class="mt-1 text-caption text-subtle">运行程序：{{ session.launcher || '当前游戏会话' }}</p>
              <p v-else class="mt-1 text-caption text-subtle">游戏文件在 HDD2 的工作副本中运行。</p>
            </div>
            <div v-if="!session.active" class="flex flex-col gap-2 sm:flex-row sm:items-center">
              <label class="sr-only" for="game-launcher">启动程序</label>
              <select id="game-launcher" v-model="selectedLauncher" class="h-10 min-w-52 rounded-lg border border-line bg-background px-3 text-meta text-ink focus-ring" :disabled="loading || !launchers.length">
                <option v-for="launcher in launchers" :key="launcher" :value="launcher">{{ launcher }}</option>
              </select>
              <UiButton variant="primary" :loading="starting" :disabled="!canStart" @click="start">
                <template #icon><Play :size="15" fill="currentColor" aria-hidden="true" /></template>
                启动游戏
              </UiButton>
            </div>
            <p v-if="session.active && !session.recoverable" class="text-caption text-warning">检测到旧会话，请停止后重新启动。</p>
          </div>
        </section>

        <p v-if="!loading && !launchers.length && !error" class="text-caption text-subtle">没有找到可启动的 EXE 文件。请确认这个游戏文件夹已完成扫描。</p>
        <p v-if="!loading && session.configured === false && !error" class="text-caption text-subtle">Linux 游戏运行底座尚未配置完成。</p>
        <p v-if="!secureBrowser" class="text-caption text-warning">浏览器串流需要 HTTPS 安全连接，请通过 HE Manager 的 HTTPS 地址打开此页面。</p>
      </div>
    </div>
  </div>
</template>
