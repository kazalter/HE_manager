<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { Check, CheckCircle2, FolderOpen, FolderPlus, HardDrive, Pipette, RefreshCw, Trash2 } from 'lucide-vue-next'
import { EmptyState, PageHeader, SectionHeader, UiBadge, UiButton, UiCard, UiIconButton, UiModal, UiSpinner, controlClass, fieldHintClass, fieldLabelClass } from '../components/ui'
import { API_BASE_URL } from '../config'
import { applyTheme, getStoredTheme, themes } from '../theme'
import type { Folder } from '../types'

const folders = ref<Folder[]>([])
const newPath = ref('')
const scanMode = ref<Folder['scan_mode']>('auto')
const thumbnailEnabled = ref(true)
const thumbnailInterval = ref(1)
const loading = ref(false)
const showAddModal = ref(false)
const selectedTheme = ref<string>(getStoredTheme())
const scanToast = ref<string | null>(null)
const externalProxy = ref('')
const loadingProxy = ref(false)
const savingProxy = ref(false)
const testingProxy = ref(false)
const proxySaved = ref(false)
const proxyError = ref('')
const proxyTestMessage = ref('')
const proxyTestSucceeded = ref(false)
let toastTimer: number | undefined
const prevScanning = ref<Set<number>>(new Set())

const showToast = (msg: string) => {
  scanToast.value = msg
  window.clearTimeout(toastTimer)
  toastTimer = window.setTimeout(() => {
    scanToast.value = null
  }, 3000)
}

const modes: Array<{ id: Folder['scan_mode']; label: string; description: string }> = [
  { id: 'auto', label: '自动', description: '自动识别视频、漫画压缩包、单张图片、单文件音频' },
  { id: 'video', label: '视频', description: '只递归扫描视频文件' },
  { id: 'image', label: '杂图', description: '只递归扫描单张图片' },
  { id: 'manga', label: '漫画', description: '把包含图片的文件夹识别为一本漫画' },
  { id: 'audio', label: '音频（单文件）', description: '每个 .mp3/.wav/.flac 单独入库（散装音乐收藏）' },
  { id: 'audio_work', label: '音频作品', description: '把每个文件夹识别为一个音频作品（ASMR 等，含 tracks.json 时优先读取）' },
]

const scanModeLabel = (mode: Folder['scan_mode']) => {
  return modes.find(item => item.id === mode)?.label || mode
}

const selectTheme = (themeId: string) => {
  selectedTheme.value = themeId
  applyTheme(themeId)
}

const fetchExternalProxy = async () => {
  loadingProxy.value = true
  proxyError.value = ''
  try {
    const res = await axios.get(`${API_BASE_URL}/external/proxy`)
    externalProxy.value = res.data.proxy || ''
  } catch (err) {
    console.error('无法读取外部收藏代理设置:', err)
    proxyError.value = '无法读取代理设置，请检查后端连接。'
  } finally {
    loadingProxy.value = false
  }
}

const saveExternalProxy = async () => {
  savingProxy.value = true
  proxySaved.value = false
  proxyError.value = ''
  proxyTestMessage.value = ''
  try {
    const res = await axios.patch(`${API_BASE_URL}/external/proxy`, {
      proxy: externalProxy.value.trim()
    })
    externalProxy.value = res.data.proxy || ''
    proxySaved.value = true
    window.setTimeout(() => {
      proxySaved.value = false
    }, 2500)
  } catch (err: any) {
    console.error('无法保存外部收藏代理设置:', err)
    const detail = err.response?.data?.detail
    proxyError.value = typeof detail === 'string' ? detail : '保存代理设置失败。'
  } finally {
    savingProxy.value = false
  }
}

const testExternalProxy = async () => {
  testingProxy.value = true
  proxySaved.value = false
  proxyError.value = ''
  proxyTestMessage.value = ''
  proxyTestSucceeded.value = false
  try {
    const res = await axios.post(`${API_BASE_URL}/external/proxy/test`, {
      proxy: externalProxy.value.trim()
    })
    proxyTestSucceeded.value = true
    proxyTestMessage.value = res.data.message || '代理连通性正常。'
  } catch (err: any) {
    console.error('外部收藏代理连通性测试失败:', err)
    const detail = err.response?.data?.detail
    proxyTestSucceeded.value = false
    proxyTestMessage.value = typeof detail === 'string' ? detail : '连通性测试失败，请检查代理地址和网络。'
  } finally {
    testingProxy.value = false
  }
}

const fetchFolders = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/folders`)
    const newFolders: Folder[] = res.data
    for (const id of prevScanning.value) {
      const f = newFolders.find(x => x.id === id)
      if (f && f.status !== 'scanning') {
        showToast(`目录「${f.path}」扫描完成！`)
      }
    }
    const currentScanning = new Set<number>()
    for (const f of newFolders) {
      if (f.status === 'scanning') currentScanning.add(f.id)
    }
    prevScanning.value = currentScanning
    folders.value = newFolders
    if (currentScanning.size > 0) {
      window.setTimeout(fetchFolders, 2000)
    }
  } catch (err) {
    console.error('无法连接到后端服务，请检查后端是否启动。', err)
  }
}

const openAddModal = () => {
  showAddModal.value = true
}

const closeAddModal = () => {
  showAddModal.value = false
  newPath.value = ''
  scanMode.value = 'auto'
  thumbnailEnabled.value = true
  thumbnailInterval.value = 1
}

const browseFolder = async () => {
  try {
    if (!('showDirectoryPicker' in window)) {
      alert('当前浏览器不支持目录选择，请手动输入绝对路径。')
      return
    }

    const dirHandle = await (window as any).showDirectoryPicker()
    const folderName = dirHandle.name
    try {
      const res = await axios.get(`${API_BASE_URL}/search-folder`, { params: { name: folderName } })
      newPath.value = res.data.results?.[0] || folderName
    } catch {
      newPath.value = folderName
    }
  } catch (err: any) {
    if (err?.name !== 'AbortError') {
      console.error('文件夹选择失败:', err)
    }
  }
}

const addFolder = async () => {
  if (!newPath.value) return
  loading.value = true
  try {
    thumbnailInterval.value = Math.min(60, Math.max(1, Number(thumbnailInterval.value) || 1))
    await axios.post(`${API_BASE_URL}/folders`, {
      path: newPath.value,
      scan_mode: scanMode.value,
      thumbnail_enabled: thumbnailEnabled.value,
      thumbnail_interval: thumbnailInterval.value,
    })
    await fetchFolders()
    closeAddModal()
  } catch (err: any) {
    const errorMsg = err.response?.data?.detail || '添加文件夹失败，请确认路径是有效的绝对路径。'
    alert(errorMsg)
  } finally {
    loading.value = false
  }
}

const scanFolder = async (id: number) => {
  const folder = folders.value.find(f => f.id === id)
  if (folder) {
    folder.status = 'scanning'
    prevScanning.value.add(id)
    showToast(`已开始扫描目录「${folder.path}」...`)
  }

  try {
    await axios.post(`${API_BASE_URL}/folders/${id}/scan`)
    window.setTimeout(fetchFolders, 1000)
  } catch (err) {
    console.error(err)
    if (folder) folder.status = 'idle'
  }
}

const isAnyScanning = computed(() => folders.value.some(f => f.status === 'scanning'))

const scanAllFolders = async () => {
  if (isAnyScanning.value) return
  const idleFolders = folders.value.filter(f => f.status !== 'scanning')
  if (idleFolders.length === 0) return

  idleFolders.forEach(f => {
    f.status = 'scanning'
    prevScanning.value.add(f.id)
  })
  showToast(`已开始扫描全部 ${idleFolders.length} 个目录...`)

  try {
    await axios.post(`${API_BASE_URL}/folders/scan-all`)
    window.setTimeout(fetchFolders, 1000)
  } catch (err) {
    console.error('一键扫描所有目录失败:', err)
    await fetchFolders()
  }
}

const removeFolder = async (id: number) => {
  if (!confirm('确定要从库中移除此目录吗？\n该操作不会删除硬盘上的文件，只会清理库中的媒体记录。')) return
  try {
    await axios.delete(`${API_BASE_URL}/folders/${id}`)
    await fetchFolders()
  } catch (err) {
    console.error(err)
  }
}

const addModalOpen = computed({
  get: () => showAddModal.value,
  set: (value: boolean) => { if (!value) closeAddModal() },
})

const shortcutGroups = [
  { title: '全局与导航', items: [['打开 / 聚焦搜索', '/ 或 Ctrl+K'], ['关闭浮层 / 弹窗', 'Esc'], ['展开 / 折叠侧栏', '点击底栏']] },
  { title: '漫画阅读器', items: [['前一页 / 后一页', '← / →'], ['重置 / 适合屏幕', '0'], ['放大 / 缩小图像', '+ / -']] },
  { title: '视频播放器', items: [['播放 / 暂停', 'Space'], ['快退 / 快进 5 秒', '← / →'], ['音量调节 / 全屏', '↑ / ↓ / F']] },
  { title: '音频与打标', items: [['音频播放 / 暂停', 'Space'], ['一键快速打星', '1 ~ 5'], ['联想选择补全标签', 'Enter']] },
]

const formatLocalTime = (timeStr: string | null) => {
  if (!timeStr) return ''
  const full = timeStr.replace('T', ' ').split('.')[0] || ''
  // "2026-10-08 21:00:00" -> "10-08 21:00" this year, "2025-10-08 21:00" otherwise.
  const minutes = full.slice(0, 16)
  return minutes.startsWith(`${new Date().getFullYear()}-`) ? minutes.slice(5) : minutes
}

onMounted(() => {
  void fetchFolders()
  void fetchExternalProxy()
})
</script>

<template>
  <div class="min-h-full">
    <PageHeader title="设置" description="配置媒体库来源、扫描行为和界面主题">
      <template #actions>
        <UiButton variant="primary" class="pointer-coarse:h-11" @click="openAddModal">
          <template #icon><FolderPlus :size="16" /></template>
          添加媒体库
        </UiButton>
      </template>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container">
        <div class="max-w-[960px] space-y-10">
          <!-- 媒体库目录 -->
          <section>
            <SectionHeader title="媒体库目录" :count="folders.length ? `${folders.length} 个` : undefined" description="扫描这些目录中的视频、漫画、图片和音频">
              <template #actions>
                <UiButton
                  v-if="folders.length > 0"
                  variant="secondary"
                  size="sm"
                  class="pointer-coarse:h-10"
                  :disabled="isAnyScanning"
                  :title="isAnyScanning ? '正在扫描目录中' : '一键刷新扫描所有已挂载目录'"
                  @click="scanAllFolders"
                >
                  <template #icon><RefreshCw :size="14" :class="{ 'animate-spin': isAnyScanning }" /></template>
                  {{ isAnyScanning ? '扫描中…' : '全部重新扫描' }}
                </UiButton>
              </template>
            </SectionHeader>

            <UiCard v-if="folders.length === 0" padding="none">
              <EmptyState compact :icon="HardDrive" title="尚未添加任何扫描来源" description="添加一个本机目录后，HE Manager 会自动识别其中的媒体。">
                <UiButton variant="secondary" size="sm" @click="openAddModal"><template #icon><FolderPlus :size="14" /></template>添加媒体库</UiButton>
              </EmptyState>
            </UiCard>

            <UiCard v-else padding="none" class="divide-y divide-line overflow-hidden">
              <div
                v-for="folder in folders"
                :key="folder.id"
                class="flex items-start gap-3 px-4 py-3.5 sm:items-center"
                :class="folder.status === 'error' ? 'bg-danger/5' : ''"
              >
                <span
                  class="mt-0.5 grid size-9 shrink-0 place-items-center rounded-lg sm:mt-0"
                  :class="folder.status === 'error' ? 'bg-danger/12 text-danger' : folder.status === 'scanning' ? 'bg-accent/15 text-accent-glow' : 'bg-surface-2 text-subtle'"
                  aria-hidden="true"
                >
                  <HardDrive :size="18" />
                </span>
                <div class="min-w-0 flex-1">
                  <p class="truncate font-mono text-meta text-ink" :title="folder.path">{{ folder.path }}</p>
                  <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-1.5">
                    <UiBadge>{{ scanModeLabel(folder.scan_mode) }}</UiBadge>
                    <UiBadge v-if="folder.scan_mode === 'video' || folder.scan_mode === 'auto'">
                      {{ folder.thumbnail_enabled ? `预览 ${folder.thumbnail_interval} 秒` : '预览关闭' }}
                    </UiBadge>
                    <span class="inline-flex items-center gap-1.5 text-caption" :class="folder.status === 'scanning' ? 'text-accent-glow' : folder.status === 'error' ? 'text-danger' : 'text-subtle'">
                      <span class="size-1.5 rounded-full" :class="folder.status === 'scanning' ? 'bg-accent animate-pulse' : folder.status === 'error' ? 'bg-danger' : 'bg-success'" aria-hidden="true"></span>
                      {{ folder.status === 'scanning' ? '扫描中' : folder.status === 'error' ? '扫描出错' : '空闲' }}
                    </span>
                    <span v-if="folder.last_scanned_at" class="whitespace-nowrap text-caption text-subtle tabular-nums" :title="folder.last_scanned_at.replace('T', ' ').split('.')[0]">上次扫描 {{ formatLocalTime(folder.last_scanned_at) }}</span>
                  </div>
                </div>
                <div class="flex shrink-0 items-center gap-1">
                  <UiIconButton :label="folder.status === 'scanning' ? '扫描中' : '重新扫描'" :disabled="folder.status === 'scanning'" @click="scanFolder(folder.id)">
                    <RefreshCw :size="16" :class="{ 'animate-spin': folder.status === 'scanning' }" />
                  </UiIconButton>
                  <UiIconButton label="从库中移除" class="hover:!bg-danger/12 hover:!text-danger" @click="removeFolder(folder.id)">
                    <Trash2 :size="16" />
                  </UiIconButton>
                </div>
              </div>
            </UiCard>
          </section>

          <!-- 界面主题 -->
          <section>
            <SectionHeader title="界面主题" description="选择全局强调色" />
            <div class="grid grid-cols-3 gap-2 sm:grid-cols-5 sm:gap-3">
              <button
                v-for="theme in themes"
                :key="theme.id"
                type="button"
                :aria-pressed="selectedTheme === theme.id"
                class="group rounded-2xl border bg-surface p-2 text-left transition-colors duration-150 focus-ring"
                :class="selectedTheme === theme.id ? 'border-accent' : 'border-line hover:border-line-strong'"
                @click="selectTheme(theme.id)"
              >
                <span class="block h-14 overflow-hidden rounded-lg border border-line p-2" :style="{ backgroundColor: theme.swatches[0] }" aria-hidden="true">
                  <span class="flex h-full items-end gap-1.5">
                    <span class="h-full flex-1 rounded-md" :style="{ backgroundColor: theme.swatches[1] }"></span>
                    <span class="h-3/5 flex-1 rounded-md" :style="{ backgroundColor: theme.swatches[1] }"></span>
                    <span class="size-4 shrink-0 self-start rounded-full" :style="{ backgroundColor: theme.swatches[2] }"></span>
                  </span>
                </span>
                <span class="mt-2 flex items-center gap-1.5 px-1 pb-0.5">
                  <span class="min-w-0 flex-1 truncate text-meta font-medium" :class="selectedTheme === theme.id ? 'text-ink' : 'text-muted'">{{ theme.name }}</span>
                  <Check v-if="selectedTheme === theme.id" :size="15" class="shrink-0 text-accent" aria-hidden="true" />
                </span>
              </button>

              <label
                class="group relative cursor-pointer rounded-2xl border bg-surface p-2 text-left transition-colors duration-150 focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-accent"
                :class="selectedTheme.startsWith('#') ? 'border-accent' : 'border-line hover:border-line-strong'"
              >
                <input
                  type="color"
                  :value="selectedTheme.startsWith('#') ? selectedTheme : '#818cf8'"
                  @input="(e) => selectTheme((e.target as HTMLInputElement).value)"
                  class="absolute h-0 w-0 opacity-0"
                  title="选择自定义颜色"
                />
                <span class="grid h-14 place-items-center rounded-lg border border-dashed border-line-strong bg-surface-2 text-subtle" aria-hidden="true">
                  <span v-if="selectedTheme.startsWith('#')" class="size-6 rounded-full" :style="{ backgroundColor: selectedTheme }"></span>
                  <Pipette v-else :size="18" />
                </span>
                <span class="pointer-events-none mt-2 flex items-center gap-1.5 px-1 pb-0.5">
                  <span class="min-w-0 flex-1 truncate text-meta font-medium" :class="selectedTheme.startsWith('#') ? 'text-ink' : 'text-muted'">自定义颜色</span>
                  <Check v-if="selectedTheme.startsWith('#')" :size="15" class="shrink-0 text-accent" aria-hidden="true" />
                </span>
              </label>
            </div>
          </section>

          <!-- 外部收藏代理 -->
          <section>
            <SectionHeader title="网络代理" description="统一用于 WNACG、X 收藏和 Pawchive 的服务端请求">
              <template #actions>
                <span v-if="loadingProxy" role="status" class="flex items-center gap-1.5 text-meta text-subtle">
                  <UiSpinner :size="14" label="正在读取" /> 正在读取
                </span>
                <span v-else-if="proxySaved" role="status" class="flex items-center gap-1.5 text-meta text-success">
                  <Check :size="14" aria-hidden="true" /> 已保存
                </span>
              </template>
            </SectionHeader>
            <UiCard padding="md">
              <form @submit.prevent="saveExternalProxy">
                <label for="external-favorites-proxy" :class="fieldLabelClass">HTTP 代理地址</label>
                <div class="flex flex-col gap-3 sm:flex-row">
                  <input
                    id="external-favorites-proxy"
                    v-model="externalProxy"
                    @input="proxyTestMessage = ''; proxyTestSucceeded = false"
                    type="url"
                    autocomplete="url"
                    :disabled="loadingProxy || savingProxy || testingProxy"
                    placeholder="例如 http://127.0.0.1:7890"
                    :class="[controlClass('md'), 'sm:flex-1']"
                  />
                  <div class="grid grid-cols-2 gap-2 sm:flex">
                    <UiButton variant="secondary" :loading="testingProxy" :disabled="loadingProxy || savingProxy || testingProxy" @click="testExternalProxy">
                      <template #icon><RefreshCw :size="16" /></template>
                      测试连通性
                    </UiButton>
                    <UiButton variant="primary" type="submit" :loading="savingProxy" :disabled="loadingProxy || savingProxy || testingProxy">
                      保存
                    </UiButton>
                  </div>
                </div>
                <p :class="fieldHintClass">留空表示直连。支持无账号密码的 HTTP 代理；该设置也会用于 Pawchive 登录、作者列表和媒体请求。</p>
                <p
                  v-if="proxyTestMessage"
                  :role="proxyTestSucceeded ? 'status' : 'alert'"
                  class="mt-3 flex items-start gap-2.5 rounded-lg border px-3.5 py-3 text-meta"
                  :class="proxyTestSucceeded ? 'border-success/25 bg-success/10 text-success' : 'border-danger/25 bg-danger/10 text-danger'"
                >{{ proxyTestMessage }}</p>
                <p v-if="proxyError" role="alert" class="mt-3 flex items-start gap-2.5 rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">{{ proxyError }}</p>
              </form>
            </UiCard>
          </section>

          <!-- 全站键盘快捷键指南 -->
          <section class="pointer-coarse:hidden">
            <SectionHeader title="键盘快捷键" description="熟悉快捷键，浏览与播放更顺手" />
            <div class="grid grid-cols-1 gap-3 sm:grid-cols-2">
              <UiCard v-for="group in shortcutGroups" :key="group.title" padding="none">
                <h3 class="px-4 pt-3.5 pb-1 text-meta font-medium text-muted">{{ group.title }}</h3>
                <dl class="px-4 pb-2">
                  <div v-for="[action, keys] in group.items" :key="action" class="flex min-h-10 items-center justify-between gap-3 border-t border-line first:border-t-0">
                    <dt class="text-body text-ink">{{ action }}</dt>
                    <dd><kbd class="inline-flex h-6 min-w-6 items-center justify-center whitespace-nowrap rounded-md border border-line-strong bg-surface-2 px-1.5 font-mono text-caption text-muted">{{ keys }}</kbd></dd>
                  </div>
                </dl>
              </UiCard>
            </div>
          </section>
        </div>
      </div>
    </div>

    <UiModal v-model:open="addModalOpen" title="添加媒体库" description="选择一个本机目录和它的识别方式" size="lg" :close-on-backdrop="false">
      <div class="space-y-6">
        <div>
          <label for="settings-new-path" :class="fieldLabelClass">文件夹绝对路径 <span class="text-danger">*</span></label>
          <div class="flex gap-2">
            <input
              id="settings-new-path"
              v-model="newPath"
              type="text"
              autofocus
              :class="[controlClass('md'), 'font-mono']"
              placeholder="例如: D:\Manga\Collection"
            />
            <UiButton variant="secondary" title="浏览文件夹" aria-label="浏览文件夹" @click="browseFolder">
              <template #icon><FolderOpen :size="16" /></template>
              <span class="hidden sm:inline">浏览</span>
            </UiButton>
          </div>
          <p :class="fieldHintClass">请确认路径在服务器上真实存在。</p>
        </div>

        <fieldset>
          <legend :class="fieldLabelClass">识别模式</legend>
          <div class="grid grid-cols-1 gap-2 sm:grid-cols-2">
            <button
              v-for="mode in modes"
              :key="mode.id"
              type="button"
              :aria-pressed="scanMode === mode.id"
              class="flex items-start gap-3 rounded-lg border px-3 py-2.5 text-left transition-colors duration-150 focus-ring"
              :class="scanMode === mode.id ? 'border-accent/50 bg-accent/10' : 'border-line bg-surface-2 hover:border-line-strong'"
              @click="scanMode = mode.id"
            >
              <span
                class="mt-1 grid size-4 shrink-0 place-items-center rounded-full border"
                :class="scanMode === mode.id ? 'border-accent bg-accent' : 'border-line-strong'"
                aria-hidden="true"
              ><span v-if="scanMode === mode.id" class="size-1.5 rounded-full bg-on-accent"></span></span>
              <span class="min-w-0">
                <span class="block text-body font-medium" :class="scanMode === mode.id ? 'text-ink' : 'text-muted'">{{ mode.label }}</span>
                <span class="mt-0.5 block text-caption text-subtle">{{ mode.description }}</span>
              </span>
            </button>
          </div>
        </fieldset>

        <div v-if="scanMode === 'video' || scanMode === 'auto'" class="rounded-lg border border-line bg-surface-2 p-4">
          <div class="flex items-center justify-between gap-4">
            <div class="min-w-0">
              <p class="text-body font-medium text-ink">生成进度条预览</p>
              <p class="mt-0.5 text-caption text-subtle">封面始终生成，此选项只影响播放器悬停预览。</p>
            </div>
            <button
              type="button"
              role="switch"
              aria-label="生成进度条预览"
              :aria-checked="thumbnailEnabled"
              :aria-pressed="thumbnailEnabled"
              class="relative h-6 w-10 shrink-0 rounded-full transition-colors focus-ring"
              :class="thumbnailEnabled ? 'bg-accent' : 'border border-line-strong bg-surface-3'"
              @click="thumbnailEnabled = !thumbnailEnabled"
            >
              <span class="absolute top-1 left-1 size-4 rounded-full bg-white transition-transform" :class="thumbnailEnabled ? 'translate-x-4' : ''" />
            </button>
          </div>

          <div :class="thumbnailEnabled ? '' : 'pointer-events-none opacity-45'" class="mt-4 border-t border-line pt-4 transition-opacity">
            <div class="mb-2 flex items-center justify-between">
              <label for="settings-thumb-interval" class="text-meta font-medium text-muted">生成间隔</label>
              <span class="text-meta text-ink tabular-nums">{{ thumbnailInterval }} 秒</span>
            </div>
            <div class="flex items-center gap-4">
              <input v-model.number="thumbnailInterval" type="range" min="1" max="60" step="1" aria-label="生成间隔（滑块）" class="flex-1 accent-accent" />
              <input id="settings-thumb-interval" v-model.number="thumbnailInterval" type="number" min="1" max="60" :class="[controlClass('md'), 'w-20 tabular-nums']" />
            </div>
            <p :class="fieldHintClass">电脑性能一般可以设为 5-10 秒；想要更细的预览就设为 1-2 秒。</p>
          </div>
        </div>
      </div>
      <template #footer>
        <UiButton variant="ghost" @click="closeAddModal">取消</UiButton>
        <UiButton variant="primary" :loading="loading" :disabled="loading || !newPath" @click="addFolder">
          <template #icon><FolderPlus :size="16" /></template>
          {{ loading ? '正在添加…' : '确认添加' }}
        </UiButton>
      </template>
    </UiModal>

    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="scanToast"
          role="status"
          class="settings-toast fixed right-6 bottom-6 z-[270] flex max-w-sm items-start gap-3 rounded-2xl border border-line-strong bg-surface-3 px-4 py-3 text-body text-ink shadow-pop"
        >
          <CheckCircle2 class="mt-0.5 shrink-0 text-info" :size="18" aria-hidden="true" />
          <span class="min-w-0 break-words">{{ scanToast }}</span>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<style scoped>
@media (max-width: 899px) {
  .settings-toast {
    left: 16px;
    right: 16px;
    max-width: none;
    bottom: calc(var(--he-nav-height, 64px) + env(safe-area-inset-bottom) + 12px);
  }
}
</style>
