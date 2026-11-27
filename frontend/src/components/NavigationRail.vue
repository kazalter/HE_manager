<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from 'vue'
import { useRoute, type RouteLocationRaw } from 'vue-router'
import {
  ArchiveX,
  BarChart3,
  Book,
  Compass,
  CopyMinus,
  Download,
  Film,
  Headphones,
  Home,
  Image as ImageIcon,
  Layers,
  LogOut,
  MessageSquare,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Search,
  Settings,
  Sparkles,
  Star,
  Tags,
  Users,
} from 'lucide-vue-next'
import ColorModeToggle from './ColorModeToggle.vue'
import { UiButton, UiModal } from './ui'
import { cycleDensity, DENSITY_OPTIONS, densityState } from '../density'
import { assistantPanelStore } from '../stores/assistantPanelStore'
import type { User } from '../types'

const props = withDefaults(defineProps<{
  user: User | null
  collapsed?: boolean
}>(), {
  collapsed: false,
})

const emit = defineEmits<{
  logout: []
  openCommandPalette: []
  toggleCollapse: []
}>()

const route = useRoute()
const logoutConfirmOpen = ref(false)

interface RailItem {
  to?: RouteLocationRaw
  label: string
  icon: typeof Home
  active?: boolean
  admin?: boolean
  onClick?: () => void
  badgeDot?: boolean
}

const isHomeActive = computed(() => route.path === '/' && route.query.favorite !== 'true')
const isFavoriteActive = computed(() => route.path === '/' && route.query.favorite === 'true')

const navSections = computed(() => {
  const isAdmin = Boolean(props.user?.is_admin)
  const sections: Array<{ label: string; items: RailItem[] }> = [
    {
      label: '媒体库',
      items: [
        { to: '/', label: '全部媒体', icon: Home, active: isHomeActive.value },
        { to: '/type/video', label: '视频', icon: Film },
        { to: '/type/manga', label: '漫画', icon: Book },
        { to: '/type/image', label: '杂图', icon: ImageIcon },
        { to: '/type/audio', label: '音频', icon: Headphones },
        { to: { path: '/', query: { favorite: 'true' } }, label: '收藏', icon: Star, active: isFavoriteActive.value },
      ],
    },
    {
      label: '发现与整理',
      items: [
        { to: '/creators', label: '创作者', icon: Users },
        { to: '/tags', label: '标签管理', icon: Tags },
        { to: '/external', label: '外部收藏', icon: Compass, admin: true },
        {
          label: '媒体库管家',
          icon: MessageSquare,
          admin: true,
          active: assistantPanelStore.state.open,
          badgeDot: assistantPanelStore.state.activeRun || assistantPanelStore.state.pendingCount > 0,
          onClick: () => assistantPanelStore.toggle(),
        },
      ],
    },
    {
      label: '系统与工具',
      items: [
        { to: '/downloads', label: '下载任务', icon: Download },
        { to: '/stats', label: '统计看板', icon: BarChart3 },
        { to: '/bd2-spine', label: 'BD2 动态', icon: Sparkles },
        { to: '/live2d', label: '碧蓝航线', icon: Palette },
        { to: '/dedup', label: '重复管理', icon: CopyMinus, admin: true },
        { to: '/discarded', label: '丢弃记录', icon: ArchiveX, admin: true },
      ],
    },
    {
      label: '管理',
      items: [
        { to: '/settings', label: '设置', icon: Settings, admin: true },
        { to: '/users', label: '用户管理', icon: Users, admin: true },
      ],
    },
  ]

  return sections
    .map(section => ({
      ...section,
      items: section.items.filter(item => !item.admin || isAdmin),
    }))
    .filter(section => section.items.length > 0)
})

const isItemActive = (item: RailItem) => {
  if (item.active !== undefined) return item.active
  if (typeof item.to === 'string') {
    if (item.to === '/creators') return route.path === '/creators' || route.path.startsWith('/creators/')
    return route.path === item.to
  }
  return false
}

const currentDensityOption = computed(
  () => DENSITY_OPTIONS.find(opt => opt.id === densityState.density) ?? DENSITY_OPTIONS[1]!,
)
const densityChangedBadge = ref(false)
let densityBadgeTimer: number | undefined
const onCycleDensity = () => {
  cycleDensity()
  densityChangedBadge.value = true
  window.clearTimeout(densityBadgeTimer)
  densityBadgeTimer = window.setTimeout(() => { densityChangedBadge.value = false }, 1500)
}

const userInitial = computed(() => (props.user?.username?.trim()[0] || 'U').toUpperCase())

const confirmLogout = () => {
  logoutConfirmOpen.value = false
  emit('logout')
}
onBeforeUnmount(() => window.clearTimeout(densityBadgeTimer))
</script>

<template>
  <aside
    aria-label="主导航栏"
    class="he-nav-rail he-glass-sidebar relative z-30 flex h-full min-h-0 flex-col select-none"
    :class="collapsed ? 'items-center px-2 py-3' : 'px-3 py-3.5'"
  >
    <!-- Brand + Collapse Toggle -->
    <div
      class="flex shrink-0 items-center"
      :class="collapsed ? 'flex-col gap-2' : 'justify-between gap-2 px-1'"
    >
      <router-link
        to="/"
        class="group flex min-w-0 items-center gap-2.5 rounded-xl px-1 py-1 focus-ring"
        :title="collapsed ? 'HE Manager 首页' : undefined"
      >
        <span class="grid size-9 shrink-0 place-items-center rounded-xl squircle bg-gradient-to-br from-accent to-accent-glow text-[13px] font-bold tracking-wider text-on-accent shadow-[inset_0_1px_0_rgb(255_255_255/0.3),0_6px_16px_-4px_rgb(var(--color-accent)/0.65)] transition-transform duration-150 group-hover:scale-[1.04]">HE</span>
        <span v-if="!collapsed" class="min-w-0">
          <span class="block truncate text-body font-semibold leading-tight tracking-tight text-ink">HE Manager</span>
          <span class="block truncate text-[11px] text-subtle">个人媒体中心</span>
        </span>
      </router-link>

      <button
        type="button"
        class="grid size-8 shrink-0 place-items-center rounded-lg text-subtle transition-colors duration-150 hover:bg-surface-2/70 hover:text-ink focus-ring"
        :title="collapsed ? '展开侧边导航 ([)' : '收起侧边导航 ([)'"
        :aria-label="collapsed ? '展开侧边导航' : '收起侧边导航'"
        :aria-expanded="!collapsed"
        @click="emit('toggleCollapse')"
      >
        <PanelLeftOpen v-if="collapsed" :size="16" aria-hidden="true" />
        <PanelLeftClose v-else :size="16" aria-hidden="true" />
      </button>
    </div>

    <!-- Command Palette Quick Launch -->
    <div class="mt-3 shrink-0" :class="collapsed ? 'w-full flex justify-center' : 'px-0.5'">
      <button
        type="button"
        class="flex h-9 items-center rounded-xl border border-line/70 bg-surface/45 text-meta text-subtle shadow-[inset_0_1px_0_var(--he-border-specular)] transition-all duration-150 hover:border-line-strong hover:bg-surface-2/70 hover:text-ink focus-ring"
        :class="collapsed ? 'size-10 justify-center' : 'w-full justify-between gap-2 px-3'"
        aria-label="打开命令面板搜索或跳转"
        :title="collapsed ? '快速跳转与搜索 (Ctrl/⌘ K)' : undefined"
        @click="emit('openCommandPalette')"
      >
        <span class="flex min-w-0 items-center gap-2">
          <Search :size="15" class="shrink-0" aria-hidden="true" />
          <span v-if="!collapsed" class="truncate">快速跳转…</span>
        </span>
        <kbd v-if="!collapsed" class="rounded-md border border-line/80 bg-surface-2/70 px-1.5 py-0.5 font-mono text-[10px] text-subtle">⌘K</kbd>
      </button>
    </div>

    <!-- Scrollable Navigation Sections -->
    <nav
      aria-label="主导航"
      class="mt-4 min-h-0 flex-1 overflow-y-auto overscroll-contain"
      :class="collapsed ? 'scrollbar-none w-full space-y-3' : 'custom-scrollbar space-y-4 px-0.5'"
    >
      <section v-for="section in navSections" :key="section.label" :aria-label="section.label">
        <p
          v-if="!collapsed"
          class="px-2.5 pb-1.5 text-[11px] font-semibold tracking-wider text-faint"
        >
          {{ section.label }}
        </p>
        <div v-else class="mx-auto mb-1.5 h-px w-6 bg-line/70" aria-hidden="true"></div>

        <div class="space-y-0.5" :class="collapsed ? 'flex flex-col items-center' : ''">
          <template v-for="item in section.items" :key="item.label">
            <router-link
              v-if="item.to"
              :to="item.to"
              :aria-current="isItemActive(item) ? 'page' : undefined"
              :title="collapsed ? item.label : undefined"
              class="group relative flex items-center rounded-xl text-meta font-medium transition-[background-color,color,box-shadow,transform] duration-150 focus-ring-inset active:scale-[0.98]"
              :class="[
                collapsed ? 'size-10 justify-center' : 'gap-2.5 px-2.5 py-2',
                isItemActive(item)
                  ? 'bg-accent/18 text-ink ring-1 ring-inset ring-accent/35 shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_4px_16px_-6px_rgb(var(--color-accent)/0.45)]'
                  : 'text-muted hover:bg-surface-2/60 hover:text-ink',
              ]"
            >
              <span
                v-if="isItemActive(item) && !collapsed"
                class="absolute left-0.5 top-2 bottom-2 w-[3px] rounded-full bg-accent shadow-[0_0_10px_rgb(var(--color-accent)/0.85)]"
                aria-hidden="true"
              ></span>
              <component
                :is="item.icon"
                :size="16"
                class="shrink-0 transition-transform duration-150 group-hover:scale-105"
                :class="isItemActive(item) ? 'text-accent-glow' : 'text-subtle group-hover:text-ink'"
                aria-hidden="true"
              />
              <span v-if="!collapsed" class="min-w-0 flex-1 truncate">{{ item.label }}</span>
              <span v-else class="sr-only">{{ item.label }}</span>
            </router-link>
            <button
              v-else
              type="button"
              :aria-pressed="isItemActive(item)"
              :title="collapsed ? item.label : undefined"
              class="group relative flex w-full items-center rounded-xl text-left text-meta font-medium transition-[background-color,color,box-shadow,transform] duration-150 focus-ring-inset active:scale-[0.98]"
              :class="[
                collapsed ? 'size-10 justify-center' : 'gap-2.5 px-2.5 py-2',
                isItemActive(item)
                  ? 'bg-accent/18 text-ink ring-1 ring-inset ring-accent/35 shadow-[inset_0_1px_0_rgb(255_255_255/0.14),0_4px_16px_-6px_rgb(var(--color-accent)/0.45)]'
                  : 'text-muted hover:bg-surface-2/60 hover:text-ink',
              ]"
              @click="item.onClick?.()"
            >
              <span
                v-if="isItemActive(item) && !collapsed"
                class="absolute left-0.5 top-2 bottom-2 w-[3px] rounded-full bg-accent shadow-[0_0_10px_rgb(var(--color-accent)/0.85)]"
                aria-hidden="true"
              ></span>
              <component
                :is="item.icon"
                :size="16"
                class="shrink-0 transition-transform duration-150 group-hover:scale-105"
                :class="isItemActive(item) ? 'text-accent-glow' : 'text-subtle group-hover:text-ink'"
                aria-hidden="true"
              />
              <span v-if="!collapsed" class="min-w-0 flex-1 truncate">{{ item.label }}</span>
              <span v-else class="sr-only">{{ item.label }}</span>
              <span
                v-if="item.badgeDot && !collapsed"
                class="size-2 shrink-0 rounded-full bg-accent shadow-[0_0_8px_rgb(var(--color-accent)/0.8)]"
                aria-hidden="true"
              ></span>
            </button>
          </template>
        </div>
      </section>
    </nav>

    <!-- Bottom Quiet Utility Dock -->
    <div
      class="mt-3 shrink-0 border-t border-line/55 pt-3"
      :class="collapsed ? 'flex w-full flex-col items-center gap-2' : 'space-y-2.5'"
    >

      <div
        class="flex items-center"
        :class="collapsed ? 'flex-col gap-1.5' : 'justify-between gap-1 px-0.5'"
      >
        <div class="flex items-center" :class="collapsed ? 'flex-col gap-1.5' : 'gap-1'">
          <ColorModeToggle compact :show-tooltip="false" />
          <button
            type="button"
            class="relative grid h-9 place-items-center rounded-xl border border-transparent text-subtle transition-[background-color,border-color,color,width] duration-150 hover:border-line hover:bg-surface-2 hover:text-ink focus-ring"
            :class="densityChangedBadge && !collapsed ? 'px-2.5 gap-1.5 inline-flex border-accent/40 bg-accent/14 text-accent-glow' : 'w-9'"
            :title="`布局舒适度：${currentDensityOption.label}（点击切换）`"
            :aria-label="`切换布局舒适度，当前：${currentDensityOption.label}`"
            @click="onCycleDensity"
          >
            <Layers :size="16" aria-hidden="true" />
            <span v-if="densityChangedBadge && !collapsed" class="text-[11px] font-medium whitespace-nowrap">{{ currentDensityOption.shortLabel }}</span>
          </button>
        </div>

        <div class="flex min-w-0 items-center gap-1.5">
          <div
            v-if="user && !collapsed"
            class="flex min-w-0 items-center gap-1.5 rounded-xl border border-line/65 bg-surface/50 pl-1.5 pr-2 py-1 shadow-[inset_0_1px_0_var(--he-border-specular)]"
            :title="user.username"
          >
            <span class="grid size-5 shrink-0 place-items-center rounded-md bg-accent/20 text-[10px] font-semibold text-accent-glow" aria-hidden="true">{{ userInitial }}</span>
            <span class="max-w-20 truncate text-caption font-medium text-muted">{{ user.username }}</span>
          </div>
          <button
            type="button"
            class="grid size-9 shrink-0 place-items-center rounded-xl text-subtle transition-colors hover:bg-danger/12 hover:text-danger focus-ring"
            title="退出登录"
            aria-label="退出登录"
            @click="logoutConfirmOpen = true"
          >
            <LogOut :size="16" aria-hidden="true" />
          </button>
        </div>
      </div>
    </div>

    <UiModal v-model:open="logoutConfirmOpen" title="退出登录" description="确定要退出当前账号吗？" size="sm">
      <p class="text-body text-muted">退出后需要重新输入账号密码才能继续访问媒体库。</p>
      <template #footer>
        <UiButton variant="ghost" autofocus @click="logoutConfirmOpen = false">取消</UiButton>
        <UiButton variant="danger" @click="confirmLogout">退出登录</UiButton>
      </template>
    </UiModal>
  </aside>
</template>
