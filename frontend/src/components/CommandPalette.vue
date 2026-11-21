<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, useId, watch } from 'vue'
import { useRouter } from 'vue-router'
import {
  ArchiveX,
  BarChart3,
  Book,
  Compass,
  CopyMinus,
  CornerDownLeft,
  Download,
  Film,
  Headphones,
  Home,
  Image as ImageIcon,
  MessageSquare,
  Moon,
  Palette,
  Search,
  Settings,
  Sparkles,
  Star,
  Sun,
  Tags,
  Users,
  X,
} from 'lucide-vue-next'
import type { User } from '../types'
import { applyTheme, themeOptionsForMode, themeState, toggleColorMode } from '../theme'

const open = defineModel<boolean>('open', { required: true })
const props = defineProps<{ user: User | null }>()

const router = useRouter()
const id = useId()
const dialogRef = ref<HTMLDialogElement | null>(null)
const panelRef = ref<HTMLElement | null>(null)
const inputRef = ref<HTMLInputElement | null>(null)
const query = ref('')
const activeIndex = ref(0)
const usesNativeModal = ref(false)
let pressedOutside = false
let restoreFocus: HTMLElement | null = null

const supportsClosedBy = typeof HTMLDialogElement !== 'undefined' && 'closedBy' in HTMLDialogElement.prototype

interface PaletteItem {
  id: string
  group: string
  label: string
  hint: string
  keywords: string
  icon: typeof Home
  action: () => void
}

const navigate = (to: string | { path: string; query?: Record<string, string> }) => {
  open.value = false
  void router.push(to)
}

const allItems = computed<PaletteItem[]>(() => {
  const isAdmin = Boolean(props.user?.is_admin)
  const trimmed = query.value.trim()
  const items: PaletteItem[] = []

  if (trimmed) {
    items.push({
      id: 'search-library',
      group: '媒体库搜索',
      label: `在媒体库中搜索「${trimmed}」`,
      hint: '回车直接搜索全部媒体',
      keywords: trimmed,
      icon: Search,
      action: () => navigate({ path: '/', query: { search: trimmed } }),
    })
  }

  const destinations: Array<Omit<PaletteItem, 'action'> & { to: string | { path: string; query?: Record<string, string> }; admin?: boolean }> = [
    { id: 'nav-all', group: '媒体库', label: '全部媒体', hint: '浏览所有视频、漫画、图片和音频', keywords: 'all home 首页 全部', icon: Home, to: '/' },
    { id: 'nav-video', group: '媒体库', label: '视频', hint: '本地与导入的视频作品', keywords: 'video 视频 mp4', icon: Film, to: '/type/video' },
    { id: 'nav-manga', group: '媒体库', label: '漫画', hint: '翻页与条漫阅读器', keywords: 'manga comic 漫画', icon: Book, to: '/type/manga' },
    { id: 'nav-image', group: '媒体库', label: '杂图', hint: '高清图片与画廊浏览', keywords: 'image gallery 杂图 图片', icon: ImageIcon, to: '/type/image' },
    { id: 'nav-audio', group: '媒体库', label: '音频', hint: 'ASMR 与音频播放列表', keywords: 'audio asmr 音频', icon: Headphones, to: '/type/audio' },
    { id: 'nav-fav', group: '媒体库', label: '我的收藏', hint: '查看已标星收藏的作品', keywords: 'favorite star 收藏', icon: Star, to: { path: '/', query: { favorite: 'true' } } },
    { id: 'nav-creators', group: '发现与整理', label: '创作者', hint: '按作者浏览 X 与漫画作品', keywords: 'creators authors 创作者 作者', icon: Users, to: '/creators' },
    { id: 'nav-tags', group: '发现与整理', label: '标签管理', hint: '整理、重命名与合并标签', keywords: 'tags 标签', icon: Tags, to: '/tags' },
    { id: 'nav-external', group: '发现与整理', label: '外部收藏', hint: 'WNACG · X · ASMR · Pawchive', keywords: 'external discover wnacg pawchive 外部收藏 发现', icon: Compass, to: '/external', admin: true },
    { id: 'nav-assistant', group: '发现与整理', label: '媒体库管家', hint: '自然语言查找、推荐与整理确认', keywords: 'assistant ai hermes 管家', icon: MessageSquare, to: '/assistant', admin: true },
    { id: 'nav-downloads', group: '系统与工具', label: '下载任务', hint: '查看服务器下载队列进度', keywords: 'downloads 下载', icon: Download, to: '/downloads' },
    { id: 'nav-stats', group: '系统与工具', label: '统计看板', hint: '容量、分布与观看活动概览', keywords: 'stats analytics 统计', icon: BarChart3, to: '/stats' },
    { id: 'nav-bd2', group: '系统与工具', label: 'BD2 动态', hint: 'Spine 角色动画鉴赏', keywords: 'bd2 spine 动态', icon: Sparkles, to: '/bd2-spine' },
    { id: 'nav-live2d', group: '系统与工具', label: '碧蓝航线', hint: 'Live2D 皮肤互动查看器', keywords: 'live2d azur 碧蓝航线', icon: Palette, to: '/live2d' },
    { id: 'nav-dedup', group: '管理', label: '重复管理', hint: '感知哈希检测并合并重复媒体', keywords: 'dedup duplicate 重复', icon: CopyMinus, to: '/dedup', admin: true },
    { id: 'nav-discarded', group: '管理', label: '丢弃记录', hint: '已移除内容与拦截记录', keywords: 'discarded trash 丢弃', icon: ArchiveX, to: '/discarded', admin: true },
    { id: 'nav-settings', group: '管理', label: '设置', hint: '媒体目录、代理、主题与快捷键', keywords: 'settings config 设置', icon: Settings, to: '/settings', admin: true },
    { id: 'nav-users', group: '管理', label: '用户管理', hint: '管理登录账号与权限', keywords: 'users accounts 用户', icon: Users, to: '/users', admin: true },
  ]

  for (const dest of destinations) {
    if (dest.admin && !isAdmin) continue
    items.push({
      id: dest.id,
      group: dest.group,
      label: dest.label,
      hint: dest.hint,
      keywords: dest.keywords,
      icon: dest.icon,
      action: () => navigate(dest.to),
    })
  }

  items.push({
    id: 'action-toggle-mode',
    group: '外观快捷操作',
    label: themeState.resolvedMode === 'dark' ? '切换到白天模式' : '切换到黑夜模式',
    hint: '切换明暗色彩外观',
    keywords: 'theme dark light mode 白天 黑夜 明暗',
    icon: themeState.resolvedMode === 'dark' ? Sun : Moon,
    action: () => {
      toggleColorMode()
      open.value = false
    },
  })

  for (const theme of themeOptionsForMode(themeState.resolvedMode)) {
    items.push({
      id: `action-theme-${theme.id}`,
      group: '外观快捷操作',
      label: `切换强调色：${theme.name}`,
      hint: theme.description,
      keywords: `theme color ${theme.name} ${theme.id} 主题 配色`,
      icon: Palette,
      action: () => {
        applyTheme(theme.id)
        open.value = false
      },
    })
  }

  return items
})

const filteredItems = computed(() => {
  const q = query.value.trim().toLowerCase()
  if (!q) return allItems.value
  return allItems.value.filter(item =>
    item.id === 'search-library'
    || item.label.toLowerCase().includes(q)
    || item.hint.toLowerCase().includes(q)
    || item.keywords.toLowerCase().includes(q)
    || item.group.toLowerCase().includes(q),
  )
})

const groupedItems = computed(() => {
  const map = new Map<string, Array<PaletteItem & { flatIndex: number }>>()
  filteredItems.value.forEach((item, flatIndex) => {
    const list = map.get(item.group) || []
    list.push({ ...item, flatIndex })
    map.set(item.group, list)
  })
  return [...map.entries()].map(([group, items]) => ({ group, items }))
})

watch(filteredItems, items => {
  if (activeIndex.value >= items.length) activeIndex.value = Math.max(0, items.length - 1)
})

const syncDialogState = async (value: boolean) => {
  await nextTick()
  const dialog = dialogRef.value
  if (!dialog) return

  if (value) {
    restoreFocus = document.activeElement as HTMLElement | null
    query.value = ''
    activeIndex.value = 0
    if (typeof dialog.showModal === 'function') {
      try {
        if (!dialog.open) dialog.showModal()
        usesNativeModal.value = true
      } catch {
        dialog.setAttribute('open', '')
        usesNativeModal.value = false
      }
    } else {
      dialog.setAttribute('open', '')
      usesNativeModal.value = false
    }
    await nextTick()
    inputRef.value?.focus()
  } else {
    if (typeof dialog.close === 'function' && dialog.open) {
      try { dialog.close() } catch { dialog.removeAttribute('open') }
    } else {
      dialog.removeAttribute('open')
    }
    if (!usesNativeModal.value) restoreFocus?.focus?.()
    restoreFocus = null
  }
}

watch(open, value => { void syncDialogState(value) }, { immediate: true })
onMounted(() => { if (open.value) void syncDialogState(true) })
onBeforeUnmount(() => {
  const dialog = dialogRef.value
  if (dialog?.open && typeof dialog.close === 'function') {
    try { dialog.close() } catch { dialog.removeAttribute('open') }
  }
})

const close = () => { open.value = false }
const onCancel = (event: Event) => { event.preventDefault(); close() }
const onNativeClose = () => { if (open.value) open.value = false }

const onKeydown = (event: KeyboardEvent) => {
  const count = filteredItems.value.length
  if (event.key === 'ArrowDown' && count) {
    event.preventDefault()
    activeIndex.value = (activeIndex.value + 1) % count
  } else if (event.key === 'ArrowUp' && count) {
    event.preventDefault()
    activeIndex.value = (activeIndex.value - 1 + count) % count
  } else if (event.key === 'Enter' && count) {
    event.preventDefault()
    filteredItems.value[activeIndex.value]?.action()
  } else if (event.key === 'Escape' && !usesNativeModal.value) {
    event.stopPropagation()
    close()
  }
}

const isOutsidePanel = (event: PointerEvent) => {
  const rect = panelRef.value?.getBoundingClientRect()
  if (!rect) return false
  return event.clientX < rect.left || event.clientX > rect.right || event.clientY < rect.top || event.clientY > rect.bottom
}
const onPointerDown = (event: PointerEvent) => {
  if (!supportsClosedBy || !usesNativeModal.value) pressedOutside = isOutsidePanel(event)
}
const onPointerUp = (event: PointerEvent) => {
  if ((!supportsClosedBy || !usesNativeModal.value) && pressedOutside && isOutsidePanel(event)) close()
  pressedOutside = false
}
</script>

<template>
  <Teleport to="body">
    <dialog
      ref="dialogRef"
      closedby="any"
      :role="usesNativeModal ? undefined : 'dialog'"
      :aria-modal="usesNativeModal ? undefined : 'true'"
      :aria-labelledby="`${id}-label`"
      class="he-palette-dialog m-0 max-h-none max-w-none border-0 bg-transparent p-0 text-ink"
      :class="{ 'is-open': open }"
      @cancel="onCancel"
      @close="onNativeClose"
      @pointerdown="onPointerDown"
      @pointerup="onPointerUp"
      @click.self="close"
    >
      <div v-if="open" class="flex h-full w-full items-start justify-center px-4 pt-[12vh]" @click.self="close">
        <section
          ref="panelRef"
          class="he-palette-panel squircle flex w-full max-w-[600px] flex-col overflow-hidden rounded-3xl border border-line-strong glass-elevated shadow-modal"
          @keydown="onKeydown"
        >
          <div class="flex items-center gap-3 border-b border-line/80 px-4 py-3">
            <Search :size="18" class="shrink-0 text-accent" aria-hidden="true" />
            <label :id="`${id}-label`" :for="`${id}-input`" class="sr-only">快速搜索与跳转</label>
            <input
              :id="`${id}-input`"
              ref="inputRef"
              v-model="query"
              type="search"
              autofocus
              autocomplete="off"
              placeholder="搜索媒体、页面或切换主题…"
              class="min-w-0 flex-1 bg-transparent text-body text-ink placeholder:text-subtle focus:outline-none"
            />
            <button
              v-if="query"
              type="button"
              class="grid size-7 place-items-center rounded-lg text-subtle transition-colors hover:bg-surface-2 hover:text-ink focus-ring"
              aria-label="清空输入"
              @click="query = ''; inputRef?.focus()"
            >
              <X :size="14" aria-hidden="true" />
            </button>
            <button
              type="button"
              class="hidden sm:inline-flex items-center rounded-md border border-line bg-surface-2 px-1.5 py-0.5 font-mono text-[11px] text-subtle hover:text-ink focus-ring"
              aria-label="关闭命令面板"
              @click="close"
            >
              ESC
            </button>
          </div>

          <div class="custom-scrollbar max-h-[min(60vh,460px)] overflow-y-auto overscroll-contain p-2">
            <template v-if="groupedItems.length">
              <div v-for="section in groupedItems" :key="section.group" class="mb-2 last:mb-0">
                <p class="px-3 py-1.5 text-caption font-medium text-subtle">{{ section.group }}</p>
                <div class="space-y-0.5">
                  <button
                    v-for="item in section.items"
                    :key="item.id"
                    type="button"
                    class="flex w-full items-center gap-3 rounded-xl px-3 py-2.5 text-left transition-colors duration-100 focus-ring-inset"
                    :class="activeIndex === item.flatIndex
                      ? 'bg-accent/15 text-ink ring-1 ring-inset ring-accent/30'
                      : 'text-muted hover:bg-surface-2/80 hover:text-ink'"
                    @mouseenter="activeIndex = item.flatIndex"
                    @click="item.action()"
                  >
                    <span
                      class="grid size-8 shrink-0 place-items-center rounded-lg border"
                      :class="activeIndex === item.flatIndex ? 'border-accent/35 bg-accent/15 text-accent-glow' : 'border-line bg-surface-2 text-subtle'"
                      aria-hidden="true"
                    >
                      <component :is="item.icon" :size="16" />
                    </span>
                    <span class="min-w-0 flex-1">
                      <span class="block truncate text-body font-medium text-ink">{{ item.label }}</span>
                      <span class="block truncate text-caption text-subtle">{{ item.hint }}</span>
                    </span>
                    <CornerDownLeft v-if="activeIndex === item.flatIndex" :size="14" class="shrink-0 text-accent" aria-hidden="true" />
                  </button>
                </div>
              </div>
            </template>
            <p v-else class="py-10 text-center text-meta text-subtle">没有匹配的指令或页面</p>
          </div>

          <footer class="hidden sm:flex items-center justify-between border-t border-line/70 px-4 py-2 text-caption text-subtle">
            <span>↑↓ 选择 · Enter 打开</span>
            <span>随时按 <kbd class="rounded border border-line bg-surface-2 px-1 font-mono text-[11px]">Ctrl/⌘ K</kbd> 唤起</span>
          </footer>
        </section>
      </div>
    </dialog>
  </Teleport>
</template>

<style>
.he-palette-dialog {
  display: none;
  position: fixed;
  inset: 0;
  width: 100%;
  height: 100%;
  z-index: 240;
  overflow: visible;
}

.he-palette-dialog[open],
.he-palette-dialog.is-open {
  display: block;
}

.he-palette-dialog:not(:modal).is-open {
  background: rgb(0 0 0 / 0.6);
}

.he-palette-dialog::backdrop {
  background: rgb(0 0 0 / 0);
  backdrop-filter: blur(0px);
  transition-property: background-color, backdrop-filter, display, overlay;
  transition-duration: 160ms;
  transition-timing-function: var(--ease-out);
  transition-behavior: allow-discrete;
}

.he-palette-dialog[open]::backdrop {
  background: rgb(0 0 0 / 0.58);
  backdrop-filter: blur(8px);
  @starting-style {
    background: rgb(0 0 0 / 0);
    backdrop-filter: blur(0px);
  }
}

.he-palette-panel {
  box-shadow: var(--he-shadow-modal), inset 0 1px 0 var(--he-border-specular);
}

@media (prefers-reduced-motion: no-preference) {
  .he-palette-dialog[open] .he-palette-panel {
    opacity: 1;
    translate: 0 0;
    scale: 1;
    transition: opacity 150ms var(--ease-out), translate 180ms var(--ease-out), scale 180ms var(--ease-out);
    @starting-style {
      opacity: 0;
      translate: 0 -10px;
      scale: 0.98;
    }
  }
}
</style>
