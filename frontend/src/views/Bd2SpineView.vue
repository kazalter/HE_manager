<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import axios from 'axios'
import { AlertCircle, Box, Download, Film, Loader2, Play, RefreshCw, Sparkles, Upload } from 'lucide-vue-next'
import { EmptyState, PageHeader, UiButton, UiSegmented, UiSpinner, buttonClass, controlClass } from '../components/ui'
import type { SpinePlayer as SpinePlayerInstance, SpinePlayerConfig } from '@esotericsoftware/spine-player'
import '@esotericsoftware/spine-player/dist/spine-player.css'
import { API_BASE_URL } from '../config'
import { authState } from '../auth'
import type { Bd2SpineAsset, Bd2SpineListResponse } from '../types'

const STORAGE_KEY = 'he_manager_bd2_target_dir'
const DEFAULT_TARGET_DIR = 'E:\\hhh\\BD2'
const SPINE_ASSET_CACHE_VERSION = 'spine41-atlas-alias-v2'

const assets = ref<Bd2SpineAsset[]>([])
const selectedId = ref('')
const selectedKind = ref<'char' | 'cutscene' | 'illust'>('char')
const hideEffectLayers = ref(false)
const loading = ref(true)

// BD2 download state
type DownloadStatus = 'idle' | 'checking' | 'cloning' | 'pulling' | 'done' | 'error' | 'cancelled'
const downloadStatus = ref<DownloadStatus>('idle')
const downloadError = ref('')
const downloadStep = ref('')
const downloadMode = ref<'' | 'clone' | 'pull'>('')
const downloadMb = ref(0)
const downloadSpeed = ref(0)   // MiB/s
const downloadPct = ref(0)
const downloadFemaleDirs = ref(0)

let _downloadPollTimer: ReturnType<typeof setInterval> | null = null
let _pollFailCount = 0
const POLL_FAIL_LIMIT = 5

const targetDir = ref(localStorage.getItem(STORAGE_KEY) || DEFAULT_TARGET_DIR)
watch(targetDir, (v) => localStorage.setItem(STORAGE_KEY, v))

const isAdmin = computed(() => Boolean(authState.user?.is_admin))
const isAuthed = computed(() => Boolean(authState.user))

const cancelDownload = async () => {
  try {
    await axios.post(`${API_BASE_URL}/bd2/spine/download/cancel`)
  } catch { /* ignore */ }
  if (_downloadPollTimer) { clearInterval(_downloadPollTimer); _downloadPollTimer = null }
  downloadStatus.value = 'cancelled'
  downloadStep.value = ''
}

const startDownload = async () => {
  downloadStatus.value = 'checking'
  downloadError.value = ''
  downloadStep.value = ''
  downloadMb.value = 0
  downloadSpeed.value = 0
  downloadPct.value = 0
  downloadMode.value = ''
  _pollFailCount = 0
  try {
    await axios.post(`${API_BASE_URL}/bd2/spine/download`, {
      target_dir: targetDir.value,
    })
    // Poll for completion
    if (_downloadPollTimer) clearInterval(_downloadPollTimer)
    _downloadPollTimer = setInterval(async () => {
      try {
        const res = await axios.get(`${API_BASE_URL}/bd2/spine/download/status`)
        const st = (res.data.status as string) || 'idle'
        downloadStep.value = (res.data.step as string) || ''
        downloadMb.value = Number(res.data.mb) || 0
        downloadSpeed.value = Number(res.data.speed_mb_s) || 0
        downloadPct.value = Number(res.data.pct) || 0
        downloadMode.value = (res.data.mode as 'clone' | 'pull') || ''
        if (res.data.female_dirs !== undefined) {
          downloadFemaleDirs.value = Number(res.data.female_dirs) || 0
        }
        if (st === 'done') {
          downloadStatus.value = 'done'
          if (_downloadPollTimer) { clearInterval(_downloadPollTimer); _downloadPollTimer = null }
          // Auto-reload the asset list so newly fetched assets show up
          // without forcing the user to hit "Refresh".
          await loadAssets()
        } else if (st === 'cancelled') {
          downloadStatus.value = 'cancelled'
          if (_downloadPollTimer) { clearInterval(_downloadPollTimer); _downloadPollTimer = null }
        } else if (st === 'error') {
          downloadStatus.value = 'error'
          downloadError.value = (res.data.error as string) || 'Unknown'
          if (_downloadPollTimer) { clearInterval(_downloadPollTimer); _downloadPollTimer = null }
        } else {
          // checking / cloning / pulling
          downloadStatus.value = st as DownloadStatus
        }
        _pollFailCount = 0
      } catch {
        _pollFailCount += 1
        if (_pollFailCount >= POLL_FAIL_LIMIT) {
          downloadStatus.value = 'error'
          downloadError.value = `与后端通信失败（${_pollFailCount} 次）`
          if (_downloadPollTimer) { clearInterval(_downloadPollTimer); _downloadPollTimer = null }
        }
      }
    }, 2000)
  } catch (err: unknown) {
    const e = err as { response?: { status?: number }, message?: string }
    if (e?.response?.status === 403) {
      downloadError.value = '需要管理员权限，请用 admin 账号登录'
    } else if (e?.response?.status === 401) {
      downloadError.value = '请先登录'
    } else {
      downloadError.value = e?.message || 'Download failed'
    }
    downloadStatus.value = 'error'
  }
}

onBeforeUnmount(() => {
  if (_downloadPollTimer) clearInterval(_downloadPollTimer)
})
const playerLoading = ref(false)
const error = ref('')
const playerError = ref('')
const sourceRoot = ref('')
const animationNames = ref<string[]>([])
const skinNames = ref<string[]>([])
const playerHost = ref<HTMLDivElement | null>(null)
let player: SpinePlayerInstance | null = null
const hiddenAttachments = new WeakMap<SpineSlot, unknown>()

type SpineSlot = {
  data?: { name?: string }
  attachment?: unknown
  setAttachment?: (attachment: unknown) => void
}

type RuntimeSpinePlayer = SpinePlayerInstance & {
  skeleton?: {
    slots?: SpineSlot[]
    data?: {
      animations?: { name: string }[]
      skins?: { name: string }[]
    }
  }
}

const effectLayerPattern = /(lighting|effect|glow|shine|spark|particle|flash|aura|blur|_light\b|\blight_)/i

const filteredAssets = computed(() => assets.value.filter((asset) => asset.kind === selectedKind.value))
const selectedAsset = computed(() => assets.value.find((asset) => asset.id === selectedId.value) || null)
const charAssetCount = computed(() => assets.value.filter((asset) => asset.kind === 'char').length)
const cutsceneAssetCount = computed(() => assets.value.filter((asset) => asset.kind === 'cutscene').length)
const illustAssetCount = computed(() => assets.value.filter((asset) => asset.kind === 'illust').length)

const assetUrl = (path: string) => {
  const separator = path.includes('?') ? '&' : '?'
  return `${API_BASE_URL}${path}${separator}v=${SPINE_ASSET_CACHE_VERSION}`
}

// Show "downloading" if a git process is actually running.
const isDownloading = computed(
  () => downloadStatus.value === 'checking'
    || downloadStatus.value === 'cloning'
    || downloadStatus.value === 'pulling',
)

const buttonLabel = computed(() => {
  if (isDownloading.value) {
    // Empty during the brief `checking` phase before the mode is known.
    if (!downloadMode.value) return '准备中…'
    return downloadMode.value === 'clone' ? '首次拉取中…' : '更新中…'
  }
  if (downloadStatus.value === 'done') return '更新'
  if (downloadStatus.value === 'error') return '重试'
  // idle / cancelled: pick based on whether the target already has a clone.
  // Backend's list endpoint exposes `root` when it resolves a checkout,
  // which only happens once .git exists.  Use the local target_dir
  // presence as a cheap hint.
  return '下载'
})

const stepLabel = computed(() => {
  switch (downloadStep.value) {
    case 'checking': return '检测已有仓库…'
    case 'cloning': return '首次拉取（sparse-checkout 走代理）…'
    case 'fetching': return '拉取远端增量…'
    case 'merging': return '重置到 origin/master…'
    case 'sparse_checkout': return '配置 sparse-checkout…'
    case 'checking_out': return 'checkout 工作区…'
    case 'checking_out_all': return 'fallback 全量 checkout…'
    default: return downloadStep.value
  }
})

const pctForBar = computed(() => Math.max(0, Math.min(100, downloadPct.value)))

const etaText = computed(() => {
  if (!isDownloading.value || downloadSpeed.value <= 0) return ''
  // We don't track total bytes, but `pct` and the live `mb` give a rough
  // estimate:  pct done = mb_done / mb_total, so  remaining = mb_done * (100-pct) / pct
  if (downloadPct.value <= 0 || downloadPct.value >= 100) return ''
  const remainingMb = downloadMb.value * (100 - downloadPct.value) / downloadPct.value
  const etaSec = remainingMb / downloadSpeed.value
  if (!isFinite(etaSec) || etaSec <= 0) return ''
  if (etaSec < 60) return `≈ ${Math.round(etaSec)}s 剩余`
  return `≈ ${Math.round(etaSec / 60)}min 剩余`
})

const setSlotAttachment = (slot: SpineSlot, attachment: unknown) => {
  if (typeof slot.setAttachment === 'function') {
    slot.setAttachment(attachment)
  } else {
    slot.attachment = attachment
  }
}

const attachmentName = (attachment: unknown) => {
  if (!attachment || typeof attachment !== 'object') return ''
  return String((attachment as { name?: string }).name || '')
}

const applyEffectLayerFilter = (targetPlayer = player) => {
  const runtimePlayer = targetPlayer as RuntimeSpinePlayer | null
  const slots = runtimePlayer?.skeleton?.slots || []
  for (const slot of slots) {
    const currentAttachment = slot.attachment
    const token = `${slot.data?.name || ''} ${attachmentName(currentAttachment)}`
    const shouldHide = hideEffectLayers.value && Boolean(currentAttachment) && effectLayerPattern.test(token)
    if (shouldHide) {
      if (!hiddenAttachments.has(slot)) {
        hiddenAttachments.set(slot, currentAttachment)
      }
      setSlotAttachment(slot, null)
    } else if (!hideEffectLayers.value && hiddenAttachments.has(slot)) {
      setSlotAttachment(slot, hiddenAttachments.get(slot) || null)
      hiddenAttachments.delete(slot)
    }
  }
}

const disposePlayer = () => {
  if (player) {
    player.dispose()
    player = null
  }
  animationNames.value = []
  skinNames.value = []
}

const loadAssets = async () => {
  loading.value = true
  error.value = ''
  try {
    const res = await axios.get<Bd2SpineListResponse>(`${API_BASE_URL}/bd2/spine`)
    assets.value = res.data.assets || []
    sourceRoot.value = res.data.root || ''
    if (!filteredAssets.value.length && selectedKind.value !== 'char' && charAssetCount.value > 0) {
      selectedKind.value = 'char'
    }
    if (!selectedId.value || !filteredAssets.value.some((asset) => asset.id === selectedId.value)) {
      selectedId.value = filteredAssets.value[0]?.id || ''
    }
  } catch (err: unknown) {
    const message = err instanceof Error ? err.message : '加载失败'
    error.value = message
    assets.value = []
    selectedId.value = ''
  } finally {
    loading.value = false
  }
}

const mountPlayer = async () => {
  const asset = selectedAsset.value
  disposePlayer()
  playerError.value = ''
  if (!asset) return
  playerLoading.value = true
  await nextTick()
  if (!playerHost.value) {
    playerLoading.value = false
    return
  }

  const config = {
    binaryUrl: assetUrl(asset.skeleton_url),
    atlasUrl: assetUrl(asset.atlas_url),
    showControls: true,
    showLoading: true,
    alpha: true,
    premultipliedAlpha: false,
    backgroundColor: '00000000',
    fullScreenBackgroundColor: '101216',
    viewport: {
      x: 0,
      y: 0,
      width: 0,
      height: 0,
      padLeft: '8%',
      padRight: '8%',
      padTop: '8%',
      padBottom: '8%',
      debugRender: false,
      transitionTime: 0.2,
      animations: {},
    },
    success: (nextPlayer: SpinePlayerInstance) => {
      const runtimePlayer = nextPlayer as RuntimeSpinePlayer
      playerLoading.value = false
      animationNames.value = runtimePlayer.skeleton?.data?.animations?.map((animation) => animation.name) || []
      skinNames.value = runtimePlayer.skeleton?.data?.skins?.map((skin) => skin.name) || []
      applyEffectLayerFilter(nextPlayer)
    },
    error: (_nextPlayer: SpinePlayerInstance, message: string) => {
      playerLoading.value = false
      playerError.value = message || 'Spine 播放器加载失败'
    },
    frame: (nextPlayer: SpinePlayerInstance) => {
      applyEffectLayerFilter(nextPlayer)
    },
  } as unknown as SpinePlayerConfig

  try {
    const { SpinePlayer } = await import('@esotericsoftware/spine-player')
    player = new SpinePlayer(playerHost.value, config)
  } catch (err: unknown) {
    playerLoading.value = false
    playerError.value = err instanceof Error ? err.message : 'Spine 播放器初始化失败'
  }
}

onMounted(loadAssets)
onBeforeUnmount(disposePlayer)
watch(selectedAsset, mountPlayer)
watch(selectedKind, () => {
  if (!filteredAssets.value.some((asset) => asset.id === selectedId.value)) {
    selectedId.value = filteredAssets.value[0]?.id || ''
  }
})
watch(hideEffectLayers, () => applyEffectLayerFilter())
</script>

<template>
  <div class="min-h-full">
    <PageHeader title="BD2 Spine 预览" description="测试 Brown Dust 2 的 .skel / .atlas / texture 三件套。这里播放的是 Spine 动画数据，不是 Cubism Live2D。">
      <template #actions>
        <UiButton variant="ghost" @click="loadAssets">
          <template #icon><RefreshCw :size="16" aria-hidden="true" /></template>
          刷新列表
        </UiButton>
      </template>

      <div class="max-w-[720px] space-y-2">
        <div class="flex items-center gap-2">
          <input
            v-model="targetDir"
            type="text"
            spellcheck="false"
            aria-label="资源仓库目录"
            :class="[controlClass('md'), 'flex-1 font-mono']"
            placeholder="git 仓库目标目录（首次会自动 clone，已有则 pull）"
            :disabled="isDownloading"
          />
          <button
            type="button"
            :class="buttonClass(isDownloading || downloadStatus === 'done' ? 'secondary' : downloadStatus === 'error' ? 'danger' : 'primary', 'md')"
            :disabled="isAuthed && !isAdmin"
            :title="isAuthed && !isAdmin ? '需要管理员权限' : isDownloading ? '点击取消' : ''"
            @click="isDownloading ? cancelDownload() : startDownload()"
          >
            <UiSpinner v-if="isDownloading" :size="16" />
            <Upload v-else-if="downloadStatus === 'done'" :size="16" aria-hidden="true" />
            <Download v-else :size="16" aria-hidden="true" />
            {{ buttonLabel }}
          </button>
        </div>
        <div v-if="isDownloading" class="space-y-1.5">
          <div class="flex items-center justify-between gap-3 text-meta text-muted">
            <span class="truncate">{{ stepLabel }}</span>
            <span class="shrink-0 tabular-nums">
              {{ pctForBar }}%
              <span class="mx-1 text-faint">·</span>{{ downloadMb.toFixed(1) }} MB
              <template v-if="downloadSpeed > 0"><span class="mx-1 text-faint">·</span>{{ downloadSpeed.toFixed(1) }} MB/s</template>
              <span class="mx-1 text-faint">·</span><span class="text-subtle">{{ etaText || '估算中' }}</span>
            </span>
          </div>
          <div class="h-1 w-full overflow-hidden rounded-sm bg-surface-3">
            <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: pctForBar + '%' }" />
          </div>
          <p v-if="downloadFemaleDirs > 0" class="text-caption text-subtle tabular-nums">目标：{{ downloadFemaleDirs }} 个女性角色目录</p>
        </div>
        <p v-else-if="downloadStatus === 'done'" class="text-caption text-success">
          已同步（{{ downloadMode === 'pull' ? '增量' : '首次' }}），点「更新」可再次拉取
        </p>
        <p v-else-if="downloadStatus === 'error'" class="truncate text-caption text-danger" :title="downloadError">
          {{ downloadError }}
        </p>
        <p v-else-if="downloadStatus === 'cancelled'" class="text-caption text-subtle">
          已取消（下次按「下载」可断点续传 .git pack）
        </p>
        <p v-else-if="!isAuthed" class="text-caption text-warning">下载需要管理员账号</p>
      </div>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container space-y-4">
        <div v-if="error" role="alert" class="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">
          <AlertCircle :size="16" class="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{{ error }}</span>
        </div>

        <div class="grid gap-4 xl:grid-cols-[300px_minmax(0,1fr)] xl:gap-6">
          <aside class="flex min-w-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface">
            <div class="flex items-center justify-between gap-3 px-4 pb-3 pt-4">
              <div class="min-w-0">
                <h2 class="text-body font-semibold text-ink">测试资源</h2>
                <p class="mt-0.5 text-meta text-subtle tabular-nums">{{ filteredAssets.length }} / {{ assets.length }} 组 Spine</p>
              </div>
              <UiSpinner v-if="loading" :size="16" label="加载中" />
            </div>
            <div class="px-3 pb-3">
              <UiSegmented
                v-model="selectedKind"
                label="资源类型"
                block
                :options="[
                  { value: 'char', label: `角色 ${charAssetCount}`, icon: Box },
                  { value: 'cutscene', label: `过场 ${cutsceneAssetCount}`, icon: Film },
                  { value: 'illust', label: `立绘 ${illustAssetCount}`, icon: Sparkles },
                ]"
              />
            </div>
            <div class="max-h-[calc(100vh-320px)] min-h-0 divide-y divide-line overflow-y-auto border-t border-line custom-scrollbar">
              <button
                v-for="asset in filteredAssets"
                :key="asset.id"
                type="button"
                class="block w-full px-4 py-3 text-left transition-colors focus-ring-inset"
                :class="selectedId === asset.id ? 'bg-accent/8 shadow-[inset_2px_0_0_rgb(var(--color-accent))]' : 'hover:bg-surface-2'"
                :aria-pressed="selectedId === asset.id"
                @click="selectedId = asset.id"
              >
                <span class="block truncate text-body font-medium" :class="selectedId === asset.id ? 'text-ink' : 'text-muted'">{{ asset.title }}</span>
                <span class="mt-0.5 block truncate text-caption text-subtle tabular-nums">{{ asset.asset_id }} · {{ asset.textures.length }} 张贴图</span>
              </button>
              <p v-if="!loading && filteredAssets.length === 0" class="px-4 py-10 text-center text-meta text-subtle">
                暂无 Spine 测试资源
              </p>
            </div>
          </aside>

          <section class="min-w-0 overflow-hidden rounded-2xl border border-line bg-surface">
            <div class="flex flex-col gap-3 border-b border-line px-4 py-3 sm:px-5 lg:flex-row lg:items-center lg:justify-between">
              <div class="min-w-0">
                <h2 class="truncate text-body font-semibold text-ink">{{ selectedAsset?.title || '未选择资源' }}</h2>
                <p class="mt-0.5 truncate font-mono text-caption text-subtle">{{ selectedAsset?.asset_id || sourceRoot || 'BD2 asset root not resolved' }}</p>
              </div>
              <div class="flex flex-wrap items-center gap-3">
                <span class="text-meta text-subtle tabular-nums">{{ animationNames.length }} 个动画 · {{ skinNames.length }} 个皮肤</span>
                <button
                  type="button"
                  :aria-pressed="hideEffectLayers"
                  class="inline-flex h-8 items-center gap-1.5 rounded-lg border px-3 text-meta font-medium transition-colors focus-ring"
                  :class="hideEffectLayers ? 'border-accent/50 bg-accent/15 text-accent-glow' : 'border-line bg-surface-2 text-muted hover:border-line-strong hover:text-ink'"
                  @click="hideEffectLayers = !hideEffectLayers"
                >
                  <Sparkles :size="14" aria-hidden="true" />
                  隐藏特效层
                </button>
              </div>
            </div>

            <div class="relative min-h-[420px] bg-black/40 sm:min-h-[620px]">
              <div ref="playerHost" class="bd2-spine-host absolute inset-0"></div>
              <div
                v-if="playerLoading"
                class="absolute inset-0 flex items-center justify-center gap-3 bg-black/45 text-meta text-white/80"
              >
                <Loader2 :size="20" class="animate-spin" aria-hidden="true" />
                加载 Spine
              </div>
              <div
                v-if="playerError"
                role="alert"
                class="absolute left-4 right-4 top-4 flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger"
              >
                <AlertCircle :size="16" class="mt-0.5 shrink-0" aria-hidden="true" />
                <div class="min-w-0">
                  <p class="font-medium">Spine 资源加载失败</p>
                  <p class="mt-1 line-clamp-3 break-all font-mono text-caption text-danger/80" :title="playerError">{{ playerError }}</p>
                </div>
              </div>
              <EmptyState
                v-if="!selectedAsset && !loading"
                class="absolute inset-0"
                :icon="Play"
                title="没有可播放的 Spine 资源"
                description="先在上方填写资源仓库目录并下载，再刷新列表。"
              />
            </div>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.bd2-spine-host :deep(.spine-player) {
  width: 100%;
  height: 100%;
  background: transparent;
}

.bd2-spine-host :deep(canvas) {
  width: 100% !important;
  height: 100% !important;
}

/* The player's own error overlay (inline-styled raw text on black) duplicates
   the playerError banner — its config.error callback always fires — so hide it. */
.bd2-spine-host :deep(.spine-player-error) {
  display: none !important;
}
</style>
