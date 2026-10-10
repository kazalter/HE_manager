<script setup lang="ts">
import { computed, type Component } from 'vue'
import { useRoute, type RouteLocationRaw } from 'vue-router'
import {
  BarChart3,
  Book,
  Box,
  CopyMinus,
  Film,
  Globe2,
  Headphones,
  Home,
  Image as ImageIcon,
  LogOut,
  MessageSquare,
  Palette,
  PanelLeftClose,
  PanelLeftOpen,
  Settings as SettingsIcon,
  Sparkles,
  Star,
  Tags,
  Users,
  X,
} from 'lucide-vue-next'
import type { User } from '../types'

const props = withDefaults(defineProps<{
  collapsed: boolean
  isCompact?: boolean
  user: User | null
}>(), {
  isCompact: false,
})

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  logout: []
}>()
const route = useRoute()

const isHomeActive = computed(() => route.path === '/' && route.query.favorite !== 'true')
const isFavoriteActive = computed(() => route.path === '/' && route.query.favorite === 'true')
const rail = computed(() => props.collapsed && !props.isCompact)

interface NavItem {
  to: RouteLocationRaw
  label: string
  icon: Component
  /** Explicit active state; otherwise the route path prefix decides. */
  active?: boolean
  admin?: boolean
}

const sections = computed(() => ([
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
      { to: '/external', label: '外部收藏', icon: Globe2, admin: true },
      { to: '/recommend', label: 'AI 推荐', icon: Sparkles },
      { to: '/assistant', label: '媒体库管家', icon: MessageSquare, admin: true },
      { to: '/creators', label: '创作者', icon: Palette },
      { to: '/tags', label: '标签管理', icon: Tags },
    ],
  },
  {
    label: '系统与工具',
    items: [
      { to: '/bd2-spine', label: 'BD2 动态', icon: Box },
      { to: '/stats', label: '统计看板', icon: BarChart3 },
      { to: '/dedup', label: '重复管理', icon: CopyMinus, admin: true },
    ],
  },
] as { label: string; items: NavItem[] }[]).map(section => ({ ...section, items: section.items.filter(item => !item.admin || props.user?.is_admin) })))

const footerItems = computed<NavItem[]>(() => [
  { to: '/settings', label: '设置', icon: SettingsIcon, admin: true },
  { to: '/users', label: '用户管理', icon: Users, admin: true },
].filter(item => !item.admin || props.user?.is_admin))

const isActive = (item: NavItem) => {
  if (item.active !== undefined) return item.active
  const path = typeof item.to === 'string' ? item.to : ''
  return !!path && (route.path === path || route.path.startsWith(path + '/'))
}

const itemClass = (active: boolean) => [
  'group relative flex items-center rounded-lg text-body font-medium transition-colors duration-150 ease-out focus-ring',
  rail.value ? 'mx-auto size-10 justify-center' : 'h-9 gap-3 px-3',
  active ? 'bg-accent/12 text-ink' : 'text-muted hover:bg-surface-2 hover:text-ink',
]

const toggle = () => {
  emit('update:collapsed', !props.collapsed)
}

const handleLogout = () => {
  if (window.confirm('确定要退出登录当前账号吗？')) {
    emit('logout')
  }
}
</script>

<template>
  <aside
    :role="isCompact && !collapsed ? 'dialog' : undefined"
    :aria-modal="isCompact && !collapsed ? 'true' : undefined"
    :aria-label="isCompact && !collapsed ? '主导航菜单' : undefined"
    :class="isCompact
      ? ['fixed left-0 top-0 z-50 h-full w-64 shadow-modal transition-transform duration-200 ease-out', collapsed ? '-translate-x-full pointer-events-none' : 'translate-x-0']
      : ['h-full transition-[width] duration-200 ease-out', collapsed ? 'w-[72px]' : 'w-60']"
    class="flex flex-col border-r border-line bg-sidebar select-none"
  >
    <!-- Brand -->
    <div class="flex h-16 shrink-0 items-center gap-3" :class="rail ? 'justify-center px-0' : 'px-4'">
      <div class="grid size-8 shrink-0 place-items-center rounded-lg bg-accent text-[13px] font-semibold tracking-wide text-on-accent">HE</div>
      <div v-if="!rail" class="min-w-0 flex-1">
        <p class="truncate text-body font-semibold leading-tight text-ink">HE Manager</p>
        <p class="truncate text-caption text-subtle">个人媒体中心</p>
      </div>
      <button
        v-if="!isCompact && !collapsed"
        type="button"
        class="grid size-8 shrink-0 place-items-center rounded-lg text-subtle transition-colors hover:bg-surface-2 hover:text-ink focus-ring"
        title="收起侧边栏"
        aria-label="收起侧边栏"
        :aria-expanded="true"
        @click="toggle"
      >
        <PanelLeftClose :size="18" aria-hidden="true" />
      </button>
      <button
        v-if="isCompact && !collapsed"
        data-mobile-close
        type="button"
        class="grid size-11 shrink-0 place-items-center rounded-lg text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-ring"
        aria-label="关闭导航菜单"
        @click="toggle"
      >
        <X :size="20" aria-hidden="true" />
      </button>
    </div>

    <button
      v-if="rail"
      type="button"
      class="mx-auto mb-1 grid size-10 shrink-0 place-items-center rounded-lg text-subtle transition-colors hover:bg-surface-2 hover:text-ink focus-ring"
      title="展开侧边栏"
      aria-label="展开侧边栏"
      :aria-expanded="false"
      @click="toggle"
    >
      <PanelLeftOpen :size="18" aria-hidden="true" />
    </button>

    <!-- Navigation -->
    <nav aria-label="主导航" class="custom-scrollbar flex-1 pb-3" :class="rail ? 'overflow-visible px-2' : 'overflow-x-hidden overflow-y-auto px-3'">
      <div v-for="(section, sectionIndex) in sections" :key="section.label" class="space-y-0.5">
        <div v-if="!rail" class="px-3 pb-1.5 text-caption font-medium text-subtle" :class="sectionIndex ? 'pt-5' : 'pt-1'">{{ section.label }}</div>
        <div v-else-if="sectionIndex" class="mx-2 my-2 border-t border-line" aria-hidden="true"></div>
        <router-link
          v-for="item in section.items"
          :key="item.label"
          :to="item.to"
          :class="itemClass(isActive(item))"
          :aria-current="isActive(item) ? 'page' : undefined"
          :title="item.label"
        >
          <component
            :is="item.icon"
            :size="18"
            class="shrink-0 transition-colors"
            :class="isActive(item) ? (item.icon === Star ? 'text-star' : 'text-accent') : 'text-subtle group-hover:text-muted'"
            :fill="item.icon === Star && isActive(item) ? 'currentColor' : 'none'"
            aria-hidden="true"
          />
          <span v-if="!rail" class="truncate">{{ item.label }}</span>
          <span v-else class="he-rail-tip">{{ item.label }}</span>
        </router-link>
      </div>
    </nav>

    <!-- Footer -->
    <div class="shrink-0 space-y-0.5 border-t border-line py-3" :class="rail ? 'px-2' : 'px-3'">
      <router-link
        v-for="item in footerItems"
        :key="item.label"
        :to="item.to"
        :class="itemClass(isActive(item))"
        :aria-current="isActive(item) ? 'page' : undefined"
        :title="item.label"
      >
        <component :is="item.icon" :size="18" class="shrink-0 transition-colors" :class="isActive(item) ? 'text-accent' : 'text-subtle group-hover:text-muted'" aria-hidden="true" />
        <span v-if="!rail" class="truncate">{{ item.label }}</span>
        <span v-else class="he-rail-tip">{{ item.label }}</span>
      </router-link>
      <button
        type="button"
        class="group relative flex w-full items-center rounded-lg text-left text-body font-medium text-muted transition-colors duration-150 ease-out hover:bg-danger/10 hover:text-danger focus-ring"
        :class="rail ? 'mx-auto size-10 justify-center' : 'h-9 gap-3 px-3'"
        title="退出登录"
        @click="handleLogout"
      >
        <LogOut :size="18" class="shrink-0 text-subtle transition-colors group-hover:text-danger" aria-hidden="true" />
        <span v-if="!rail" class="truncate">退出登录</span>
        <span v-else class="he-rail-tip">退出登录</span>
      </button>
    </div>
  </aside>
</template>

<style>
/* Collapsed-rail tooltip; shown on hover and keyboard focus. */
.he-rail-tip {
  position: absolute;
  left: calc(100% + 10px);
  top: 50%;
  z-index: 50;
  padding: 4px 8px;
  border: 1px solid rgb(var(--color-line-strong));
  border-radius: 6px;
  background: rgb(var(--color-surface-3));
  box-shadow: var(--shadow-pop);
  color: rgb(var(--color-ink));
  font-size: 0.75rem;
  white-space: nowrap;
  pointer-events: none;
  opacity: 0;
  transform: translate(-4px, -50%);
  transition: opacity var(--duration-fast) var(--ease-out), transform var(--duration-fast) var(--ease-out);
}

.group:hover > .he-rail-tip,
.group:focus-visible > .he-rail-tip {
  opacity: 1;
  transform: translate(0, -50%);
}
</style>
