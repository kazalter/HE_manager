<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authState, logout } from './auth'
import { ChevronUp, MessageSquare } from 'lucide-vue-next'
import { desktopBridge, desktopSession } from './desktop'
import DesktopToolbar from './components/DesktopToolbar.vue'
import NavigationRail from './components/NavigationRail.vue'
import TopBar from './components/TopBar.vue'
import MobileNavigation from './components/MobileNavigation.vue'
import CommandPalette from './components/CommandPalette.vue'
import ClockWeather from './components/ClockWeather.vue'
import { AsyncAssistantSidebar as AssistantSidebar } from './components/asyncComponents'
import AuthView from './views/AuthView.vue'
import AppUpdateNotice from './components/AppUpdateNotice.vue'
import GlobalAudioPlayer from './components/GlobalAudioPlayer.vue'
import { audioPlaybackStore } from './stores/audioPlaybackStore'
import { assistantPanelStore } from './stores/assistantPanelStore'
import { ambientCoverStore } from './stores/ambientCoverStore'
import { useCompactViewport } from './composables/useCompactViewport'
import { useDesktopRailViewport } from './composables/useDesktopRailViewport'
import { useStandaloneViewport } from './composables/useStandaloneViewport'

const compact = useCompactViewport()
const isWideDesktop = useDesktopRailViewport()
useStandaloneViewport()
const route = useRoute(), router = useRouter()
const commandPaletteOpen = ref(false)
const railCollapsed = ref((() => {
  try { return localStorage.getItem('he_rail_collapsed') === 'true' } catch { return false }
})())
const toggleRail = () => {
  railCollapsed.value = !railCollapsed.value
  try { localStorage.setItem('he_rail_collapsed', String(railCollapsed.value)) } catch { /* optional */ }
}

watch(() => desktopSession.generation, () => {
  audioPlaybackStore.stop()
  assistantPanelStore.reset()
  const query = { ...route.query }; delete query.media
  if (route.query.media) void router.replace({ path: route.path, query })
})
watch(() => [authState.user?.id, authState.user?.is_admin], ([, isAdmin]) => {
  if (!isAdmin) assistantPanelStore.reset()
})
watch(() => route.path, path => {
  if (path === '/assistant' && assistantPanelStore.state.open) {
    assistantPanelStore.close()
  }
  if (path !== '/' && !path.startsWith('/type/')) {
    ambientCoverStore.clearCover()
  }
})
const mainScrollRef = ref<HTMLElement | null>(null)
const showBackToTop = ref(false)
const chromeRetracted = ref(false)
let lastScrollTop = 0
const isEmbed = computed(() => route.path.endsWith('/embed') || route.query.embed === 'true')
const showRail = computed(() => !isEmbed.value && !compact.value && isWideDesktop.value)
const showTopBar = computed(() => !isEmbed.value && !compact.value && !isWideDesktop.value)
const showAssistantHost = computed(() =>
  !isEmbed.value && Boolean(authState.user?.is_admin) && assistantPanelStore.state.activated && route.path !== '/assistant',
)

const scrollKey = (path: string) => {
  const [pathname, query = ''] = path.split('?')
  const params = new URLSearchParams(query)
  params.delete('media')
  params.sort()
  return pathname + '?' + params.toString()
}
const positions = new Map<string, number>()
let pendingPosition: number | null = null
const restoreScroll = () => {
  if (pendingPosition === null || !mainScrollRef.value) return
  mainScrollRef.value.scrollTo({ top: pendingPosition, behavior: 'instant' as ScrollBehavior })
  showBackToTop.value = pendingPosition > 360
  lastScrollTop = pendingPosition
  chromeRetracted.value = false
}
watch(() => route.fullPath, async (next, previous) => {
  chromeRetracted.value = false
  if (scrollKey(next) === scrollKey(previous)) return
  positions.set(scrollKey(previous), mainScrollRef.value?.scrollTop || 0)
  pendingPosition = positions.get(scrollKey(next)) || 0
  await nextTick()
  restoreScroll()
})
const onContentReady = () => { restoreScroll(); pendingPosition = null }
let scrollRafId = 0
let latestScrollEl: HTMLElement | null = null
const flushMainScroll = () => {
  scrollRafId = 0
  const el = latestScrollEl
  if (!el) return
  const y = Math.max(0, el.scrollTop)
  const nextBackToTop = y > 360
  if (showBackToTop.value !== nextBackToTop) showBackToTop.value = nextBackToTop
  if (showRail.value) return
  const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight)
  const clampedY = Math.min(y, maxScroll)
  if (clampedY <= 72) {
    chromeRetracted.value = false
    lastScrollTop = clampedY
    return
  }
  const delta = clampedY - lastScrollTop
  if (Math.abs(delta) >= 12) {
    chromeRetracted.value = delta > 0
    lastScrollTop = clampedY
  }
}
const handleMainScroll = (event: Event) => {
  latestScrollEl = event.target as HTMLElement
  if (scrollRafId) return
  scrollRafId = window.requestAnimationFrame(flushMainScroll)
}
const scrollToTop = () => {
  chromeRetracted.value = false
  mainScrollRef.value?.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
}
const retryProgress = () => { void desktopBridge?.retryProgress().catch(() => {}) }
const pauseAudioForVideo = (event: Event) => { if (event.target instanceof HTMLVideoElement && audioPlaybackStore.state.playing) audioPlaybackStore.togglePlay() }
const onGlobalKeydown = (event: KeyboardEvent) => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k') {
    if (!authState.user || isEmbed.value || route.query.media) return
    event.preventDefault()
    commandPaletteOpen.value = !commandPaletteOpen.value
    return
  }
  if (event.key === '[' && !event.metaKey && !event.ctrlKey && !event.altKey && showRail.value && authState.user && !route.query.media && !commandPaletteOpen.value) {
    const target = event.target as HTMLElement | null
    if (target && (target.tagName === 'INPUT' || target.tagName === 'TEXTAREA' || target.tagName === 'SELECT' || target.isContentEditable)) return
    event.preventDefault()
    toggleRail()
  }
}
onMounted(() => {
  window.addEventListener('online', retryProgress)
  window.addEventListener('he:content-ready', onContentReady)
  window.addEventListener('he:scroll-top', scrollToTop)
  window.addEventListener('keydown', onGlobalKeydown)
  document.addEventListener('play', pauseAudioForVideo, true)
})
onBeforeUnmount(() => {
  if (scrollRafId) window.cancelAnimationFrame(scrollRafId)
  window.removeEventListener('online', retryProgress)
  window.removeEventListener('he:content-ready', onContentReady)
  window.removeEventListener('he:scroll-top', scrollToTop)
  window.removeEventListener('keydown', onGlobalKeydown)
  document.removeEventListener('play', pauseAudioForVideo, true)
})
</script>
<template>
  <DesktopToolbar v-if="desktopBridge" />
  <AuthView v-if="authState.ready && !authState.user" :has-users="authState.hasUsers" :startup-error="authState.error" />
  <div
    v-else-if="authState.ready"
    :key="desktopBridge ? desktopSession.generation : undefined"
    class="he-app-shell w-full bg-background text-ink font-sans relative overflow-hidden"
    :class="[
      showRail ? 'he-studio-shell' : 'flex flex-col',
      {
        'is-rail-collapsed': showRail && railCollapsed,
        'he-compact-shell': compact && !isEmbed,
        'he-has-mini': audioPlaybackStore.state.media && !audioPlaybackStore.state.expanded,
      },
    ]"
  >
    <a href="#he-main-content" class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-xl focus:bg-accent focus:px-4 focus:py-3 focus:text-on-accent">跳转到主要内容</a>
    <div v-if="!isEmbed" class="he-ambient-stage" aria-hidden="true">
      <Transition name="he-ambient-fade">
        <img
          v-if="ambientCoverStore.state.coverUrl"
          :key="ambientCoverStore.state.coverUrl"
          :src="ambientCoverStore.state.coverUrl"
          alt=""
          class="he-ambient-cover-img"
        />
      </Transition>
      <div class="he-ambient-scrim"></div>
    </div>
    <div v-if="!isEmbed" class="he-ambient" aria-hidden="true"></div>
    <NavigationRail
      v-if="showRail"
      :user="authState.user"
      :collapsed="railCollapsed"
      class="he-shell-rail"
      @logout="logout"
      @open-command-palette="commandPaletteOpen = true"
      @toggle-collapse="toggleRail"
    />
    <header
      v-if="showRail"
      aria-label="顶部工具栏"
      class="he-shell-topbar he-glass-topbar relative z-30 flex h-12 shrink-0 items-center justify-end gap-2.5 px-5 lg:px-7"
    >
      <ClockWeather compact />
      <button
        v-if="authState.user?.is_admin"
        type="button"
        class="relative inline-flex h-8.5 items-center gap-2 rounded-full border px-3.5 text-meta font-medium transition-all duration-150 focus-ring"
        :class="assistantPanelStore.state.open
          ? 'border-accent/50 bg-accent/18 text-ink ring-1 ring-inset ring-accent/35 shadow-[0_0_18px_-4px_rgb(var(--color-accent)/0.55)]'
          : 'border-white/10 bg-surface/50 text-muted backdrop-blur-md hover:border-line-strong hover:bg-surface-2/75 hover:text-ink'"
        :aria-expanded="assistantPanelStore.state.open"
        aria-controls="he-assistant-sidebar"
        title="打开或收起媒体库管家右侧边栏"
        @click="assistantPanelStore.toggle()"
      >
        <MessageSquare :size="14" :class="assistantPanelStore.state.open ? 'text-accent-glow' : 'text-subtle'" aria-hidden="true" />
        <span>媒体库管家</span>
        <span
          v-if="assistantPanelStore.state.pendingCount > 0"
          class="inline-flex min-w-4 items-center justify-center rounded-full bg-accent px-1 text-[10px] font-semibold tabular-nums text-on-accent"
        >{{ assistantPanelStore.state.pendingCount }}</span>
        <span
          v-else-if="assistantPanelStore.state.activeRun"
          class="size-2 rounded-full bg-accent animate-pulse"
          aria-hidden="true"
        ></span>
      </button>
    </header>
    <TopBar
      v-if="showTopBar"
      :user="authState.user"
      :retracted="chromeRetracted"
      @logout="logout"
      @open-command-palette="commandPaletteOpen = true"
    />
    <main
      id="he-main-content"
      ref="mainScrollRef"
      :inert="audioPlaybackStore.state.expanded || !!route.query.media"
      tabindex="-1"
      @scroll.passive="handleMainScroll"
      class="he-shell-main he-scroll-state-host flex-1 min-h-0 min-w-0 relative z-10 box-border main-scroll-container focus:outline-none"
      :class="isEmbed ? 'overflow-hidden' : 'overflow-y-auto overflow-x-hidden custom-scrollbar'"
    >
      <router-view v-slot="{ Component }"><transition name="page-fade" mode="out-in"><component :is="Component" /></transition></router-view>
      <div v-if="!isEmbed" class="h-10 w-full"></div>
    </main>
    <AssistantSidebar
      v-if="showAssistantHost"
      :open="assistantPanelStore.state.open"
      @close="assistantPanelStore.close()"
    />
    <MobileNavigation v-if="compact && !isEmbed" :retracted="chromeRetracted" :inert="audioPlaybackStore.state.expanded || !!route.query.media" /><GlobalAudioPlayer v-if="!isEmbed" /><AppUpdateNotice v-if="!isEmbed" />
    <CommandPalette v-if="!isEmbed" v-model:open="commandPaletteOpen" :user="authState.user" />
    <button v-if="showBackToTop && !isEmbed && !route.query.media && !audioPlaybackStore.state.expanded" type="button" @click="scrollToTop" class="he-back-top fixed right-6 z-30 size-11 rounded-2xl squircle border border-line-strong glass-elevated text-muted shadow-pop flex items-center justify-center transition-colors duration-150 hover:text-ink focus-ring" aria-label="返回顶部"><ChevronUp :size="20" aria-hidden="true" /></button>
  </div>
  <div v-else class="he-app-shell bg-background text-subtle text-body flex flex-col items-center justify-center gap-3">
    <span class="grid size-11 place-items-center rounded-2xl bg-accent/15 text-sm font-bold tracking-wider text-accent-glow ring-1 ring-inset ring-accent/30">HE</span>
    <span>正在检查登录状态</span>
  </div>
</template>
<style>
.he-studio-shell {
  --he-rail-width: 224px;
  display: grid;
  grid-template-areas:
    "rail topbar"
    "rail main";
  grid-template-columns: var(--he-rail-width) minmax(0, 1fr);
  grid-template-rows: auto minmax(0, 1fr);
  transition: grid-template-columns var(--duration-slow) var(--ease-snappy);
}

.he-studio-shell.is-rail-collapsed {
  --he-rail-width: 68px;
}

.he-shell-rail {
  grid-area: rail;
  min-width: 0;
  min-height: 0;
}

.he-shell-topbar {
  grid-area: topbar;
  min-width: 0;
}

.he-shell-main {
  grid-area: main;
}

@media (prefers-reduced-motion: reduce) {
  .he-studio-shell {
    transition: none;
  }
}

.main-scroll-container {
  overscroll-behavior-y: contain;
}

/* Top-bar layout: the scroll area shares the shell height with the header. */
.he-app-shell.flex-col > .main-scroll-container {
  height: auto;
}

/* Atmospheric multi-pole ambient mesh behind everything; never animated. */
.he-ambient {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  contain: strict;
  transform: translateZ(0);
  background:
    radial-gradient(1280px 680px at 16% -14% var(--in-oklab), rgb(var(--color-accent) / 0.14), rgb(var(--color-accent) / 0.035) 46%, transparent 78%),
    radial-gradient(920px 560px at 88% 6% var(--in-oklab), rgb(var(--color-accent-glow) / 0.065), transparent 72%),
    radial-gradient(760px 480px at 50% 108% var(--in-oklab), rgb(var(--color-accent) / 0.05), transparent 72%);
}

.page-fade-enter-active {
  transition: opacity 220ms var(--ease-out), translate 240ms var(--ease-snappy);
}

.page-fade-leave-active {
  transition: opacity 110ms ease-in;
}

.page-fade-enter-from {
  opacity: 0;
  translate: 0 6px;
}

.page-fade-leave-to {
  opacity: 0;
}

@media (prefers-reduced-motion: reduce) {
  .page-fade-enter-from {
    translate: none;
  }
}
</style>
