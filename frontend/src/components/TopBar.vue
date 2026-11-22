<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, type RouteLocationRaw } from 'vue-router'
import {
  ArchiveX,
  BarChart3,
  Book,
  ChevronDown,
  Compass,
  CopyMinus,
  Download,
  Film,
  Headphones,
  Home,
  Image as ImageIcon,
  LayoutGrid,
  LogOut,
  MessageSquare,
  Palette,
  Search,
  Settings,
  Sparkles,
  Star,
  Tags,
  Users,
} from 'lucide-vue-next'
import ColorModeToggle from './ColorModeToggle.vue'
import ClockWeather from './ClockWeather.vue'
import { UiButton, UiModal } from './ui'
import type { User } from '../types'

const props = withDefaults(defineProps<{ user: User | null; retracted?: boolean }>(), {
  retracted: false,
})
const emit = defineEmits<{ logout: []; openCommandPalette: [] }>()

const route = useRoute()
const organizeOpen = ref(false)
const organizeRoot = ref<HTMLElement | null>(null)
const logoutConfirmOpen = ref(false)

const isHomeActive = computed(() => route.path === '/' && route.query.favorite !== 'true')
const isFavoriteActive = computed(() => route.path === '/' && route.query.favorite === 'true')

interface NavItem {
  to: RouteLocationRaw
  label: string
  icon: typeof Home
  active?: boolean
}
interface OrganizeItem {
  to: string
  label: string
  hint: string
  icon: typeof Home
  admin?: boolean
}

const library = computed<NavItem[]>(() => [
  { to: '/', label: '全部媒体', icon: Home, active: isHomeActive.value },
  { to: '/type/video', label: '视频', icon: Film },
  { to: '/type/manga', label: '漫画', icon: Book },
  { to: '/type/image', label: '杂图', icon: ImageIcon },
  { to: '/type/audio', label: '音频', icon: Headphones },
  { to: { path: '/', query: { favorite: 'true' } }, label: '收藏', icon: Star, active: isFavoriteActive.value },
])

const organizeSections = computed(() => ([
  {
    label: '发现与整理',
    items: [
      { to: '/creators', label: '创作者', hint: '作者作品集', icon: Users },
      { to: '/tags', label: '标签管理', hint: '合并与整理', icon: Tags },
      { to: '/external', label: '外部收藏', hint: '同步外部站点', icon: Compass, admin: true },
      { to: '/assistant', label: '媒体库管家', hint: '智能查找推荐', icon: MessageSquare, admin: true },
    ],
  },
  {
    label: '系统与工具',
    items: [
      { to: '/downloads', label: '下载任务', hint: '服务器队列', icon: Download },
      { to: '/stats', label: '统计看板', hint: '库概览数据', icon: BarChart3 },
      { to: '/bd2-spine', label: 'BD2 动态', hint: '角色骨骼鉴赏', icon: Sparkles },
      { to: '/live2d', label: '碧蓝航线', hint: 'Live2D 图鉴', icon: Palette },
      { to: '/discarded', label: '丢弃记录', hint: '清理与拦截', icon: ArchiveX, admin: true },
      { to: '/dedup', label: '重复管理', hint: '相似媒体清理', icon: CopyMinus, admin: true },
    ],
  },
  {
    label: '管理',
    items: [
      { to: '/settings', label: '设置', hint: '目录代理与主题', icon: Settings, admin: true },
      { to: '/users', label: '用户管理', hint: '账号与权限', icon: Users, admin: true },
    ],
  },
] as { label: string; items: OrganizeItem[] }[]).map(section => ({
  ...section,
  items: section.items.filter(item => !item.admin || props.user?.is_admin),
})).filter(section => section.items.length > 0))

const isActive = (item: NavItem) => {
  if (item.active !== undefined) return item.active
  if (typeof item.to === 'string') return route.path === item.to
  return false
}

const isOrganizeRouteActive = computed(() =>
  organizeSections.value.some(section => section.items.some(item => route.path === item.to || route.path.startsWith(item.to + '/'))),
)

const userInitial = computed(() => (props.user?.username?.trim()[0] || 'U').toUpperCase())

const closeOrganize = () => { organizeOpen.value = false }
const onDocPointer = (event: MouseEvent) => {
  if (organizeRoot.value && !organizeRoot.value.contains(event.target as Node)) closeOrganize()
}
watch(organizeOpen, open => {
  if (open) document.addEventListener('mousedown', onDocPointer)
  else document.removeEventListener('mousedown', onDocPointer)
})
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocPointer))

const confirmLogout = () => {
  logoutConfirmOpen.value = false
  emit('logout')
}
</script>

<template>
  <header
    class="he-topbar sticky top-0 z-40 flex h-14 shrink-0 items-center gap-3 border-b border-line/80 glass-surface px-4 lg:px-6"
    :class="{ 'is-retracted': retracted }"
  >
    <router-link to="/" class="group flex shrink-0 items-center gap-2.5 rounded-xl px-1 py-1 focus-ring">
      <span class="grid size-9 place-items-center rounded-xl squircle bg-accent text-[13px] font-bold tracking-wider text-on-accent shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_4px_12px_-3px_rgb(var(--color-accent)/0.55)] transition-transform duration-150 group-hover:scale-[1.03]">HE</span>
      <span class="hidden min-w-0 sm:block">
        <span class="block truncate text-body font-semibold leading-tight tracking-tight text-ink">HE Manager</span>
        <span class="block truncate text-[11px] text-subtle">个人媒体中心</span>
      </span>
    </router-link>

    <nav aria-label="主导航" class="flex min-w-0 flex-1 items-center overflow-x-auto scrollbar-none">
      <div class="inline-flex items-center gap-0.5 rounded-xl border border-line/90 bg-surface-2/75 p-1 shadow-[inset_0_1px_0_var(--he-border-specular)]">
        <router-link
          v-for="item in library"
          :key="item.label"
          :to="item.to"
          :aria-current="isActive(item) ? 'page' : undefined"
          class="relative flex shrink-0 items-center gap-1.5 rounded-lg px-3 py-1.5 text-meta font-medium transition-[background-color,color,box-shadow] duration-150 focus-ring-inset"
          :class="isActive(item)
            ? 'bg-surface-3 text-ink ring-1 ring-inset ring-accent/35 shadow-[0_1px_3px_rgb(0_0_0/0.25),inset_0_1px_0_var(--he-border-specular)]'
            : 'text-muted hover:bg-surface-3/45 hover:text-ink'"
        >
          <component :is="item.icon" :size="15" :class="isActive(item) ? 'text-accent-glow' : 'text-subtle'" aria-hidden="true" />
          <span>{{ item.label }}</span>
        </router-link>
      </div>
    </nav>

    <div class="flex shrink-0 items-center gap-1.5">
      <button
        type="button"
        class="hidden lg:inline-flex h-9 items-center gap-2 rounded-xl border border-line bg-surface-2/85 px-3 text-meta text-subtle transition-colors duration-150 hover:border-line-strong hover:bg-surface-3 hover:text-ink focus-ring"
        aria-label="打开命令面板搜索或跳转"
        @click="emit('openCommandPalette')"
      >
        <Search :size="14" aria-hidden="true" />
        <span>快速跳转…</span>
        <kbd class="ml-1 rounded border border-line-strong bg-surface px-1.5 py-0.5 font-mono text-[10px] text-subtle">⌘K</kbd>
      </button>

      <div ref="organizeRoot" class="relative shrink-0" @keydown.esc.stop="closeOrganize">
        <button
          type="button"
          class="flex h-9 items-center gap-1.5 rounded-xl border px-3 text-meta font-medium transition-colors duration-150 focus-ring"
          :class="organizeOpen || isOrganizeRouteActive
            ? 'border-accent/40 bg-accent/12 text-ink'
            : 'border-transparent text-muted hover:border-line hover:bg-surface-2/85 hover:text-ink'"
          :aria-expanded="organizeOpen"
          aria-controls="organize-tools"
          @click="organizeOpen = !organizeOpen"
        >
          <LayoutGrid :size="15" :class="isOrganizeRouteActive ? 'text-accent-glow' : 'text-subtle'" aria-hidden="true" />
          <span>更多</span>
          <ChevronDown :size="14" class="text-subtle transition-transform duration-150" :class="organizeOpen ? 'rotate-180' : ''" aria-hidden="true" />
        </button>
        <Transition name="he-pop">
          <div
            v-if="organizeOpen"
            id="organize-tools"
            role="navigation"
            aria-label="更多功能"
            class="custom-scrollbar absolute right-0 top-full z-50 mt-2 max-h-[calc(100dvh-5rem)] w-[min(420px,calc(100vw-24px))] overflow-y-auto rounded-2xl squircle border border-line-strong glass-elevated p-3 shadow-pop"
          >
            <div class="space-y-3">
              <section v-for="section in organizeSections" :key="section.label">
                <p class="px-2 pb-1.5 text-caption font-medium text-subtle">{{ section.label }}</p>
                <div class="grid grid-cols-2 gap-1.5">
                  <router-link
                    v-for="item in section.items"
                    :key="item.label"
                    :to="item.to"
                    :title="item.hint"
                    :aria-current="route.path === item.to ? 'page' : undefined"
                    class="group flex items-center gap-2.5 rounded-xl border px-2.5 py-2 text-left transition-colors duration-150 focus-ring-inset"
                    :class="route.path === item.to
                      ? 'border-accent/40 bg-accent/12 text-ink'
                      : 'border-transparent bg-surface-2/40 text-muted hover:border-line hover:bg-surface-2 hover:text-ink'"
                    @click="closeOrganize"
                  >
                    <span
                      class="grid size-8 shrink-0 place-items-center rounded-lg border"
                      :class="route.path === item.to ? 'border-accent/35 bg-accent/15 text-accent-glow' : 'border-line bg-surface-2 text-subtle group-hover:text-ink'"
                      aria-hidden="true"
                    >
                      <component :is="item.icon" :size="15" />
                    </span>
                    <span class="min-w-0 flex-1 truncate text-meta font-medium text-ink">{{ item.label }}</span>
                  </router-link>
                </div>
              </section>
            </div>
          </div>
        </Transition>
      </div>

      <ClockWeather compact />
      <ColorModeToggle compact :show-tooltip="false" />

      <div v-if="user" class="hidden xl:flex items-center gap-2 rounded-xl border border-line bg-surface-2/70 pl-1.5 pr-2.5 py-1">
        <span class="grid size-6 place-items-center rounded-lg bg-accent/20 text-[11px] font-semibold text-accent-glow" aria-hidden="true">{{ userInitial }}</span>
        <span class="max-w-28 truncate text-caption font-medium text-muted" :title="user.username">{{ user.username }}</span>
      </div>

      <button
        type="button"
        class="grid size-9 place-items-center rounded-xl text-subtle transition-colors hover:bg-danger/12 hover:text-danger focus-ring"
        title="退出登录"
        aria-label="退出登录"
        @click="logoutConfirmOpen = true"
      >
        <LogOut :size="17" aria-hidden="true" />
      </button>
    </div>

    <UiModal v-model:open="logoutConfirmOpen" title="退出登录" description="确定要退出当前账号吗？" size="sm">
      <p class="text-body text-muted">退出后需要重新输入账号密码才能继续访问媒体库。</p>
      <template #footer>
        <UiButton variant="ghost" autofocus @click="logoutConfirmOpen = false">取消</UiButton>
        <UiButton variant="danger" @click="confirmLogout">退出登录</UiButton>
      </template>
    </UiModal>
  </header>
</template>
