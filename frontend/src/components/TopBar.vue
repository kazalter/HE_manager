<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, type RouteLocationRaw } from 'vue-router'
import { Book, ChevronDown, Film, Headphones, Home, Image as ImageIcon, Star } from 'lucide-vue-next'
import ColorModeToggle from './ColorModeToggle.vue'
import GeneratedNavigationIcon from './GeneratedNavigationIcon.vue'
import ClockWeather from './ClockWeather.vue'
import { themeState } from '../theme'
import type { User } from '../types'

const props = defineProps<{ user: User | null }>()
const emit = defineEmits<{ logout: [] }>()

const route = useRoute()
const organizeOpen = ref(false)
const organizeRoot = ref<HTMLElement | null>(null)

const isHomeActive = computed(() => route.path === '/' && route.query.favorite !== 'true')
const isFavoriteActive = computed(() => route.path === '/' && route.query.favorite === 'true')

interface NavItem {
  to: RouteLocationRaw
  label: string
  icon: typeof Home
  art: 'home' | 'video' | 'manga' | 'image' | 'audio' | 'favorite'
  active?: boolean
  admin?: boolean
}
interface OrganizeItem { to: string; label: string; x: number; y: number; admin?: boolean }

const libraryItems: NavItem[] = [
  { to: '/', label: '全部媒体', icon: Home, art: 'home', active: isHomeActive.value },
  { to: '/type/video', label: '视频', icon: Film, art: 'video' },
  { to: '/type/manga', label: '漫画', icon: Book, art: 'manga' },
  { to: '/type/image', label: '杂图', icon: ImageIcon, art: 'image' },
  { to: '/type/audio', label: '音频', icon: Headphones, art: 'audio' },
  { to: { path: '/', query: { favorite: 'true' } }, label: '收藏', icon: Star, art: 'favorite', active: isFavoriteActive.value },
]

// Recomputed (not a plain const) so the home/favorite active state follows the route.
const library = computed(() => libraryItems.map(item => ({
  ...item,
  active: item.label === '全部媒体' ? isHomeActive.value : item.label === '收藏' ? isFavoriteActive.value : undefined,
})))

const organizeSections = computed(() => ([
  {
    label: '发现与整理',
    items: [
      { to: '/creators', label: '创作者', x: 166, y: 164 },
      { to: '/tags', label: '标签管理', x: 389, y: 164 },
      { to: '/recommend', label: 'AI 推荐', x: 612, y: 164 },
      { to: '/external', label: '外部收藏', x: 166, y: 388, admin: true },
      { to: '/assistant', label: '媒体库管家', x: 389, y: 388, admin: true },
    ],
  },
  {
    label: '系统与工具',
    items: [
      { to: '/downloads', label: '下载任务', x: 612, y: 388 },
      { to: '/bd2-spine', label: 'BD2 动态', x: 166, y: 611 },
      { to: '/stats', label: '统计看板', x: 389, y: 611 },
      { to: '/discarded', label: '丢弃记录', x: 612, y: 611, admin: true },
      { to: '/dedup', label: '重复管理', x: 166, y: 835, admin: true },
    ],
  },
  {
    label: '管理',
    items: [
      { to: '/settings', label: '设置', x: 389, y: 835, admin: true },
      { to: '/users', label: '用户管理', x: 612, y: 835, admin: true },
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

const closeOrganize = () => { organizeOpen.value = false }
const onDocPointer = (event: MouseEvent) => {
  if (organizeRoot.value && !organizeRoot.value.contains(event.target as Node)) closeOrganize()
}
watch(organizeOpen, open => {
  if (open) document.addEventListener('mousedown', onDocPointer)
  else document.removeEventListener('mousedown', onDocPointer)
})
onBeforeUnmount(() => document.removeEventListener('mousedown', onDocPointer))

const handleLogout = () => {
  if (window.confirm('确定要退出登录当前账号吗？')) emit('logout')
}
</script>

<template>
  <header class="he-topbar relative z-40 flex h-16 shrink-0 items-center gap-4 border-b border-line bg-sidebar px-4 lg:px-6">
    <router-link to="/" class="flex shrink-0 items-center gap-3 focus-ring rounded-lg">
      <span class="grid size-8 place-items-center rounded-lg bg-accent text-[13px] font-semibold tracking-wide text-on-accent">HE</span>
      <span class="min-w-0">
        <span class="block truncate text-body font-semibold leading-tight text-ink">HE Manager</span>
        <span class="block truncate text-caption text-subtle">个人媒体中心</span>
      </span>
    </router-link>

    <nav aria-label="主导航" class="flex min-w-0 flex-1 items-center gap-1 overflow-x-auto scrollbar-none">
      <router-link
        v-for="item in library"
        :key="item.label"
        :to="item.to"
        :aria-current="isActive(item) ? 'page' : undefined"
        class="flex shrink-0 items-center gap-2 rounded-lg px-3 py-2 text-body font-medium transition-colors duration-150 focus-ring"
        :class="isActive(item) ? 'bg-accent/12 text-ink' : 'text-muted hover:bg-surface-2 hover:text-ink'"
      >
        <GeneratedNavigationIcon :name="item.art" />
        <span>{{ item.label }}</span>
      </router-link>
    </nav>

      <div ref="organizeRoot" class="relative shrink-0" @keydown.esc.stop="closeOrganize">
        <button
          type="button"
          class="flex items-center gap-1.5 rounded-lg px-3 py-2 text-body font-medium transition-colors duration-150 focus-ring"
          :class="organizeOpen ? 'bg-surface-2 text-ink' : 'text-muted hover:bg-surface-2 hover:text-ink'"
          :aria-expanded="organizeOpen"
          aria-controls="organize-tools"
          @click="organizeOpen = !organizeOpen"
        >
          更多
          <ChevronDown :size="15" class="transition-transform duration-150" :class="organizeOpen ? 'rotate-180' : ''" aria-hidden="true" />
        </button>
        <Transition name="he-pop">
        <div
          v-if="organizeOpen"
          id="organize-tools"
          role="navigation"
          aria-label="更多功能"
          class="custom-scrollbar absolute right-0 top-full z-50 mt-2 max-h-[calc(100dvh-5rem)] w-64 overflow-y-auto rounded-2xl border border-line-strong bg-surface p-1.5 shadow-pop"
        >
          <template v-for="section in organizeSections" :key="section.label">
            <p class="px-2.5 pb-1 pt-2 text-caption font-medium text-subtle">{{ section.label }}</p>
            <router-link
              v-for="item in section.items"
              :key="item.label"
              :to="item.to"
              class="flex items-center gap-3 rounded-lg px-2.5 py-2 text-body text-muted transition-colors hover:bg-surface-2 hover:text-ink focus-ring"
              @click="closeOrganize"
            ><span class="he-organize-icon" :style="{ '--icon-x': item.x + (themeState.resolvedMode === 'dark' ? 760 : 0), '--icon-y': item.y }" aria-hidden="true"></span><span>{{ item.label }}</span></router-link>
          </template>
        </div>
        </Transition>
      </div>

    <div class="flex shrink-0 items-center gap-1">
      <ClockWeather compact />
      <ColorModeToggle compact generated-icon :show-tooltip="false" />
      <span v-if="user" class="hidden max-w-32 truncate px-2 text-meta text-muted xl:block" :title="user.username">{{ user.username }}</span>
      <button
        type="button"
        class="grid size-10 place-items-center rounded-lg text-subtle transition-colors hover:bg-surface-2 hover:text-ink focus-ring"
        title="退出登录"
        aria-label="退出登录"
        @click="handleLogout"
      >
        <GeneratedNavigationIcon name="logout" />
      </button>
    </div>
  </header>
</template>

<style scoped>
/* The generated sheet contains the same twelve icons in light and dark variants. */
.he-organize-icon {
  display: block;
  flex: none;
  width: 24px;
  height: 24px;
  border-radius: 50%;
  filter: grayscale(1);
  background-image: url('../assets/organize-icons-generated.png');
  background-size: 192px 128px;
  background-position: calc(12px - var(--icon-x) * 0.125px) calc(12px - var(--icon-y) * 0.125px);
  background-repeat: no-repeat;
}
</style>
