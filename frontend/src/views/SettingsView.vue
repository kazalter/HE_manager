<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { FolderOpen, FolderPlus, HardDrive, Image as ImageIcon, Keyboard, Palette, RefreshCw, Sparkles, Timer, Trash2, X } from 'lucide-vue-next'
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

const formatLocalTime = (timeStr: string | null) => {
  if (!timeStr) return ''
  return timeStr.replace('T', ' ').split('.')[0]
}

onMounted(fetchFolders)
</script>

<template>
  <div class="p-6 md:p-8 max-w-5xl mx-auto z-10 relative">
    <header class="mb-10 flex flex-wrap justify-between items-end gap-5">
      <div>
        <h1 class="text-3xl md:text-4xl font-black mb-3 text-white">偏好设置</h1>
        <p class="text-white/50 text-base md:text-lg">配置媒体库来源、扫描行为和界面主题。</p>
      </div>
      <button @click="openAddModal" class="bg-accent hover:bg-accent-glow text-white px-5 py-3 rounded-xl font-semibold flex items-center gap-2 transition-all shadow-lg shadow-accent/20 active:scale-95">
        <FolderPlus :size="20" />
        添加媒体库
      </button>
    </header>

    <div class="space-y-8">
      <section class="border border-white/6 bg-white/[0.02] backdrop-blur-3xl rounded-3xl p-5 md:p-6 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)]">
        <div class="flex items-center justify-between mb-4">
          <div class="flex items-center gap-2.5">
            <Palette class="text-accent" :size="20" />
            <h2 class="text-base font-bold text-white/90">界面主题</h2>
            <span class="text-xs text-white/40">选择全局高亮配色</span>
          </div>
        </div>

        <div class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-2.5">
          <button
            v-for="theme in themes"
            :key="theme.id"
            type="button"
            @click="selectTheme(theme.id)"
            :aria-pressed="selectedTheme === theme.id"
            :class="selectedTheme === theme.id ? 'border-accent bg-accent/15 text-white ring-1 ring-accent/30 shadow-md shadow-accent/10' : 'border-white/8 bg-white/[0.02] text-white/75 hover:bg-white/5 hover:border-white/15'"
            class="group relative text-left rounded-xl border p-2.5 transition-all flex items-center gap-2.5 cursor-pointer"
          >
            <div class="flex shrink-0">
              <span
                v-for="color in theme.swatches.slice(0, 2)"
                :key="color"
                class="w-4 h-4 rounded-full border border-white/20 -mr-1 shadow-sm"
                :style="{ backgroundColor: color }"
              ></span>
            </div>
            <div class="min-w-0 flex-1">
              <p class="font-bold text-xs text-white truncate">{{ theme.name }}</p>
            </div>
            <span v-if="selectedTheme === theme.id" class="w-2 h-2 rounded-full bg-accent shrink-0 ring-2 ring-accent/30"></span>
          </button>

          <!-- Custom Theme Picker -->
          <label
            :class="selectedTheme.startsWith('#') ? 'border-accent bg-accent/15 text-white ring-1 ring-accent/30 shadow-md shadow-accent/10' : 'border-white/8 bg-white/[0.02] text-white/75 hover:bg-white/5 hover:border-white/15'"
            class="relative text-left rounded-xl border p-2.5 transition-all flex items-center gap-2.5 cursor-pointer"
          >
            <input 
              type="color" 
              :value="selectedTheme.startsWith('#') ? selectedTheme : '#818cf8'"
              @input="(e) => selectTheme((e.target as HTMLInputElement).value)"
              class="absolute opacity-0 w-0 h-0"
              title="选择自定义颜色"
            />
            <span
              class="w-4 h-4 rounded-full shrink-0 border border-white/20 shadow-sm"
              :style="selectedTheme.startsWith('#') ? { backgroundColor: selectedTheme } : { background: 'linear-gradient(135deg, #ff0000, #ffff00, #00ffff, #9400d3)' }"
            ></span>
            <div class="min-w-0 flex-1 pointer-events-none">
              <p class="font-bold text-xs text-white truncate">自定义颜色</p>
            </div>
            <span v-if="selectedTheme.startsWith('#')" class="w-2 h-2 rounded-full bg-accent shrink-0 ring-2 ring-accent/30"></span>
          </label>
        </div>
      </section>

      <section class="border border-white/6 bg-white/[0.02] backdrop-blur-3xl rounded-3xl p-6 md:p-8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)]">
        <div class="flex items-center justify-between gap-4 mb-6">
          <h2 class="text-xs font-black tracking-wider uppercase text-white/55 flex items-center gap-3">
            <HardDrive class="text-emerald-400" :size="18" />
            已挂载目录
            <span v-if="folders.length > 0" class="text-white/30 text-[11px] font-mono font-normal">({{ folders.length }})</span>
          </h2>

          <button
            v-if="folders.length > 0"
            @click="scanAllFolders"
            :disabled="isAnyScanning"
            class="h-9 px-3.5 rounded-xl bg-white/5 hover:bg-accent/20 hover:text-accent border border-white/10 hover:border-accent/30 flex items-center gap-2 transition-all disabled:opacity-50 disabled:pointer-events-none active:scale-95 text-xs font-bold text-white/80 cursor-pointer shadow-sm"
            :title="isAnyScanning ? '正在扫描目录中' : '一键刷新扫描所有已挂载目录'"
          >
            <RefreshCw :class="{ 'animate-spin text-accent': isAnyScanning }" :size="14" />
            <span>{{ isAnyScanning ? '扫描中...' : '一键刷新所有目录' }}</span>
          </button>
        </div>

        <div v-if="folders.length === 0" class="text-center py-12 border border-dashed border-white/10 rounded-xl bg-white/[0.01]">
          <p class="text-white/35 font-medium text-sm">尚未添加任何扫描来源</p>
        </div>

        <div v-else class="space-y-4">
          <div
            v-for="folder in folders"
            :key="folder.id"
            class="group relative flex flex-wrap items-center justify-between gap-4 p-5 bg-white/[0.01] hover:bg-white/5 border rounded-xl shadow-[inset_0_1px_0_rgba(255,255,255,0.02)] transition-all duration-300"
            :class="folder.status === 'scanning' ? 'border-accent/40 bg-accent/[0.04]' : 'border-white/8'"
          >
            <div class="min-w-0 flex-1">
              <p class="font-mono text-sm md:text-base text-white/90 break-all" :title="folder.path">{{ folder.path }}</p>
              <div class="flex flex-wrap items-center gap-3 mt-2">
                <span class="text-[10px] font-black bg-white/10 px-2 py-0.5 rounded border border-white/10 text-white/65">
                  {{ scanModeLabel(folder.scan_mode) }}
                </span>
                <span v-if="folder.scan_mode === 'video' || folder.scan_mode === 'auto'" class="text-[10px] font-black bg-white/10 px-2 py-0.5 rounded border border-white/10 text-white/65">
                  {{ folder.thumbnail_enabled ? `预览间隔 ${folder.thumbnail_interval} 秒` : '进度预览关闭' }}
                </span>
                <p class="text-sm flex items-center gap-2" :class="folder.status === 'scanning' ? 'text-accent font-bold' : 'text-white/80'">
                  <span v-if="folder.status === 'scanning'" class="relative flex h-2.5 w-2.5">
                    <span class="animate-ping absolute inline-flex h-full w-full rounded-full bg-accent opacity-75"></span>
                    <span class="relative inline-flex rounded-full h-2.5 w-2.5 bg-accent"></span>
                  </span>
                  <span v-else class="w-2 h-2 rounded-full bg-emerald-400"></span>
                  {{ folder.status === 'scanning' ? '深度扫描中...' : '空闲' }}
                  <span class="text-white/50 font-normal" v-if="folder.last_scanned_at">
                    上次扫描: {{ formatLocalTime(folder.last_scanned_at) }}
                  </span>
                </p>
              </div>
            </div>

            <div class="flex gap-2 shrink-0">
              <button
                @click="scanFolder(folder.id)"
                :disabled="folder.status === 'scanning'"
                class="h-11 px-3 rounded-xl bg-white/5 hover:bg-accent/20 hover:text-accent flex items-center justify-center gap-2 transition-all disabled:opacity-50 active:scale-95"
                title="重新扫描"
              >
                <RefreshCw :class="{ 'animate-spin text-accent': folder.status === 'scanning' }" :size="20" />
                <span class="hidden lg:inline text-xs font-bold">{{ folder.status === 'scanning' ? '扫描中' : '重新扫描' }}</span>
              </button>

              <button
                @click="removeFolder(folder.id)"
                class="h-11 px-3 rounded-xl bg-red-500/5 border border-red-400/10 text-red-300/70 hover:bg-red-500/15 hover:text-red-200 hover:border-red-400/25 flex items-center justify-center gap-2 transition-all active:scale-95"
                title="从库中移除"
              >
                <Trash2 :size="20" />
                <span class="hidden lg:inline text-xs font-bold">移除</span>
              </button>
            </div>
          </div>
        </div>
      </section>

      <!-- 全站键盘快捷键指南 -->
      <section class="border border-white/6 bg-white/[0.02] backdrop-blur-3xl rounded-3xl p-6 md:p-8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.05),0_12px_32px_-8px_rgba(0,0,0,0.4)]">
        <div class="flex items-center gap-3 mb-6">
          <Keyboard class="text-accent" :size="22" />
          <div>
            <h2 class="text-lg font-bold text-white/90">全站键盘快捷键指南</h2>
            <p class="text-xs text-white/45 mt-0.5">熟悉快捷键可获得极致流畅的浏览与播放体验</p>
          </div>
        </div>

        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-4 space-y-3">
            <h3 class="text-xs font-black uppercase text-accent tracking-wider">全局与导航</h3>
            <div class="space-y-2 text-xs">
              <div class="flex items-center justify-between"><span class="text-white/60">打开 / 聚焦搜索</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">/ 或 Ctrl+K</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">关闭浮层 / 弹窗</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">Esc</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">展开 / 折叠侧栏</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">点击底栏</kbd></div>
            </div>
          </div>

          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-4 space-y-3">
            <h3 class="text-xs font-black uppercase text-accent tracking-wider">漫画阅读器</h3>
            <div class="space-y-2 text-xs">
              <div class="flex items-center justify-between"><span class="text-white/60">前一页 / 后一页</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">← / →</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">重置 / 适合屏幕</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">0</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">放大 / 缩小图像</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">+ / -</kbd></div>
            </div>
          </div>

          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-4 space-y-3">
            <h3 class="text-xs font-black uppercase text-accent tracking-wider">视频播放器</h3>
            <div class="space-y-2 text-xs">
              <div class="flex items-center justify-between"><span class="text-white/60">播放 / 暂停</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">Space</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">快退 / 快进 5秒</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">← / →</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">音量调节 / 全屏</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">↑ / ↓ / F</kbd></div>
            </div>
          </div>

          <div class="rounded-2xl border border-white/8 bg-white/[0.02] p-4 space-y-3">
            <h3 class="text-xs font-black uppercase text-accent tracking-wider">音频与打标</h3>
            <div class="space-y-2 text-xs">
              <div class="flex items-center justify-between"><span class="text-white/60">音频播放 / 暂停</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">Space</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">一键快速打星</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">1 ~ 5</kbd></div>
              <div class="flex items-center justify-between"><span class="text-white/60">联想选择补全标签</span><kbd class="px-2 py-0.5 rounded bg-white/10 border border-white/15 text-white/85 font-mono text-[11px]">Enter</kbd></div>
            </div>
          </div>
        </div>
      </section>
    </div>

    <Teleport to="body">
      <div v-if="showAddModal" class="fixed inset-0 z-[200] flex items-center justify-center">
        <div class="absolute inset-0 bg-background/80 backdrop-blur-sm" @click="closeAddModal"></div>

        <div class="relative w-full max-w-2xl bg-sidebar/95 backdrop-blur-xl border border-white/10 rounded-2xl p-6 md:p-8 shadow-2xl m-4">
          <div class="flex justify-between items-center mb-7">
            <h2 class="text-2xl font-bold flex items-center gap-3 text-white/90">
              <FolderPlus class="text-accent" />
              添加新来源
            </h2>
            <button @click="closeAddModal" class="text-white/45 hover:text-white transition-colors w-10 h-10 rounded-xl hover:bg-white/5 flex items-center justify-center">
              <X :size="23" />
            </button>
          </div>

          <div class="space-y-6">
            <div>
              <label class="block text-xs font-bold text-white/45 uppercase tracking-widest mb-2 ml-1">文件夹绝对路径</label>
              <div class="flex gap-2">
                <input
                  v-model="newPath"
                  type="text"
                  class="flex-1 min-w-0 bg-black/35 border border-white/10 rounded-xl px-4 py-3.5 text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-accent focus:border-transparent transition-all"
                  placeholder="例如: D:\Manga\Collection"
                />
                <button
                  @click="browseFolder"
                  class="shrink-0 bg-white/5 hover:bg-white/10 border border-white/10 rounded-xl px-4 py-3 text-white/70 hover:text-white transition-all flex items-center gap-2 active:scale-95"
                  title="浏览文件夹"
                >
                  <FolderOpen :size="20" />
                  <span class="text-sm font-medium hidden sm:inline">浏览</span>
                </button>
              </div>
            </div>

            <div>
              <label class="block text-xs font-bold text-white/45 uppercase tracking-widest mb-2 ml-1">识别模式</label>
              <div class="grid grid-cols-2 md:grid-cols-4 gap-3">
                <button
                  v-for="mode in modes"
                  :key="mode.id"
                  @click="scanMode = mode.id"
                  :class="scanMode === mode.id ? 'bg-accent/20 border-accent text-white' : 'bg-white/5 border-white/10 text-white/50 hover:bg-white/10'"
                  class="flex flex-col items-start p-4 rounded-xl border transition-all text-left min-h-[104px]"
                >
                  <span class="text-sm font-black uppercase tracking-widest mb-1">{{ mode.label }}</span>
                  <span class="text-xs opacity-70 leading-relaxed">{{ mode.description }}</span>
                </button>
              </div>
            </div>

            <div v-if="scanMode === 'video' || scanMode === 'auto'" class="rounded-xl border border-white/10 bg-black/20 p-5 space-y-5">
              <div class="flex items-center justify-between gap-4">
                <div class="flex items-center gap-3">
                  <div class="w-10 h-10 rounded-xl bg-accent/15 text-accent flex items-center justify-center">
                    <ImageIcon :size="20" />
                  </div>
                  <div>
                    <p class="text-sm font-bold text-white/90">生成进度条预览</p>
                    <p class="text-xs text-white/45 mt-0.5">封面始终生成，此选项只影响播放器悬停预览。</p>
                  </div>
                </div>
                <button
                  type="button"
                  @click="thumbnailEnabled = !thumbnailEnabled"
                  :class="thumbnailEnabled ? 'bg-accent' : 'bg-white/10'"
                  class="relative w-12 h-7 rounded-full transition-colors shrink-0"
                  :aria-pressed="thumbnailEnabled"
                >
                  <span
                    :class="thumbnailEnabled ? 'translate-x-5' : 'translate-x-1'"
                    class="absolute top-1 left-0 w-5 h-5 rounded-full bg-white transition-transform"
                  ></span>
                </button>
              </div>

              <div :class="thumbnailEnabled ? 'opacity-100' : 'opacity-40 pointer-events-none'" class="transition-opacity">
                <div class="flex items-center justify-between mb-2">
                  <label class="text-xs font-bold text-white/50 uppercase tracking-widest flex items-center gap-2">
                    <Timer :size="14" />
                    生成间隔
                  </label>
                  <span class="text-sm font-mono text-white/80">{{ thumbnailInterval }} 秒</span>
                </div>
                <div class="flex items-center gap-4">
                  <input v-model.number="thumbnailInterval" type="range" min="1" max="60" step="1" class="flex-1 accent-indigo-400" />
                  <input v-model.number="thumbnailInterval" type="number" min="1" max="60" class="w-20 bg-black/35 border border-white/10 rounded-xl px-3 py-2 text-sm text-white focus:outline-none focus:ring-2 focus:ring-accent/60" />
                </div>
                <p class="text-xs text-white/35 mt-2">电脑性能一般可以设为 5-10 秒；想要更细的预览就设为 1-2 秒。</p>
              </div>
            </div>

            <div class="flex items-center justify-between pt-5 border-t border-white/10 gap-4">
              <p class="text-sm text-white/45 flex items-center gap-2">
                <HardDrive :size="14" /> 请确认路径在本机真实存在
              </p>
              <button
                @click="addFolder"
                :disabled="loading"
                class="bg-accent hover:bg-accent-glow text-white px-6 py-3 rounded-xl font-bold flex items-center gap-2 transition-all disabled:opacity-50 active:scale-95"
              >
                <RefreshCw v-if="loading" class="animate-spin" :size="18" />
                <FolderPlus v-else :size="18" />
                {{ loading ? '正在扫描...' : '确认添加' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>

    <Teleport to="body">
      <Transition name="fade">
        <div
          v-if="scanToast"
          class="fixed bottom-6 right-6 z-[300] flex items-center gap-2.5 rounded-2xl border border-accent/30 bg-sidebar/95 px-5 py-3 text-sm font-bold text-white shadow-2xl backdrop-blur-xl"
        >
          <Sparkles class="text-accent shrink-0" :size="18" />
          <span>{{ scanToast }}</span>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>
