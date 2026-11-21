<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { authState, logout } from './auth'
import { ChevronUp } from 'lucide-vue-next'
import { desktopBridge, desktopSession } from './desktop'
import DesktopToolbar from './components/DesktopToolbar.vue'
import NavigationRail from './components/NavigationRail.vue'
import TopBar from './components/TopBar.vue'
import MobileNavigation from './components/MobileNavigation.vue'
import CommandPalette from './components/CommandPalette.vue'
import AuthView from './views/AuthView.vue'
import AppUpdateNotice from './components/AppUpdateNotice.vue'
import GlobalAudioPlayer from './components/GlobalAudioPlayer.vue'
import { audioPlaybackStore } from './stores/audioPlaybackStore'
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
  const query = { ...route.query }; delete query.media
  if (route.query.media) void router.replace({ path: route.path, query })
})
const mainScrollRef = ref<HTMLElement | null>(null)
const showBackToTop = ref(false)
const chromeRetracted = ref(false)
let lastScrollTop = 0
const isEmbed = computed(() => route.path.endsWith('/embed') || route.query.embed === 'true')
const showRail = computed(() => !isEmbed.value && !compact.value && isWideDesktop.value)
const showTopBar = computed(() => !isEmbed.value && !compact.value && !isWideDesktop.value)

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
const handleMainScroll = (event: Event) => {
  const el = event.target as HTMLElement
  const maxScroll = Math.max(0, el.scrollHeight - el.clientHeight)
  const y = Math.max(0, Math.min(el.scrollTop, maxScroll))
  showBackToTop.value = y > 360
  if (y <= 72) {
    chromeRetracted.value = false
    lastScrollTop = y
    return
  }
  const delta = y - lastScrollTop
  if (Math.abs(delta) >= 12) {
    chromeRetracted.value = delta > 0
    lastScrollTop = y
  }
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
      @scroll="handleMainScroll"
      class="he-shell-main he-scroll-state-host flex-1 min-h-0 min-w-0 relative z-10 box-border main-scroll-container focus:outline-none"
      :class="isEmbed ? 'overflow-hidden' : 'overflow-y-auto overflow-x-hidden custom-scrollbar'"
    >
      <router-view v-slot="{ Component }"><transition name="page-fade" mode="out-in"><component :is="Component" /></transition></router-view>
      <div v-if="!isEmbed" class="h-10 w-full"></div>
    </main>
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
  --he-rail-width: 236px;
  display: grid;
  grid-template-areas: "rail main";
  grid-template-columns: var(--he-rail-width) minmax(0, 1fr);
  grid-template-rows: minmax(0, 1fr);
  transition: grid-template-columns var(--duration-base) var(--ease-out);
}

.he-studio-shell.is-rail-collapsed {
  --he-rail-width: 72px;
}

.he-shell-rail {
  grid-area: rail;
  min-width: 0;
  min-height: 0;
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
  background:
    radial-gradient(1200px 640px at 18% -15% var(--in-oklab), rgb(var(--color-accent) / 0.1), rgb(var(--color-accent) / 0.025) 45%, transparent 78%),
    radial-gradient(900px 520px at 88% 8% var(--in-oklab), rgb(var(--color-accent-glow) / 0.045), transparent 72%);
}

.page-fade-enter-active {
  transition: opacity var(--duration-base) var(--ease-out), translate var(--duration-base) var(--ease-out);
}

.page-fade-leave-active {
  transition: opacity var(--duration-fast) ease-in;
}

.page-fade-enter-from {
  opacity: 0;
  translate: 0 4px;
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
