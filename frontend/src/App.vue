<script setup lang="ts">
import { computed, nextTick, onMounted, onBeforeUnmount, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { authState, logout } from './auth'
import { ChevronUp } from 'lucide-vue-next'
import Sidebar from './components/Sidebar.vue'
import MobileNavigation from './components/MobileNavigation.vue'
import AuthView from './views/AuthView.vue'
import AppUpdateNotice from './components/AppUpdateNotice.vue'
import GlobalAudioPlayer from './components/GlobalAudioPlayer.vue'
import { audioPlaybackStore } from './stores/audioPlaybackStore'
import { useCompactViewport } from './composables/useCompactViewport'
import { useStandaloneViewport } from './composables/useStandaloneViewport'
const compact = useCompactViewport()
useStandaloneViewport()
const desktopCollapsed = ref(localStorage.getItem('he_sidebar_collapsed') === 'true')
watch(desktopCollapsed, value => localStorage.setItem('he_sidebar_collapsed', String(value)))
const route = useRoute()
const mainScrollRef = ref<HTMLElement | null>(null)
const showBackToTop = ref(false)
const isEmbed = computed(() => route.path.endsWith('/embed') || route.query.embed === 'true')
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
}
watch(() => route.fullPath, async (next, previous) => {
  if (scrollKey(next) === scrollKey(previous)) return
  positions.set(scrollKey(previous), mainScrollRef.value?.scrollTop || 0)
  pendingPosition = positions.get(scrollKey(next)) || 0
  await nextTick()
  restoreScroll()
})
const onContentReady = () => { restoreScroll(); pendingPosition = null }
const handleMainScroll = (event: Event) => { showBackToTop.value = (event.target as HTMLElement).scrollTop > 360 }
const scrollToTop = () => mainScrollRef.value?.scrollTo({ top: 0, behavior: window.matchMedia('(prefers-reduced-motion: reduce)').matches ? 'auto' : 'smooth' })
const pauseAudioForVideo = (event: Event) => { if (event.target instanceof HTMLVideoElement && audioPlaybackStore.state.playing) audioPlaybackStore.togglePlay() }
onMounted(() => { window.addEventListener('he:content-ready', onContentReady); document.addEventListener('play', pauseAudioForVideo, true) })
onBeforeUnmount(() => { window.removeEventListener('he:content-ready', onContentReady); document.removeEventListener('play', pauseAudioForVideo, true) })
</script>
<template>
  <AuthView v-if="authState.ready && !authState.user" :has-users="authState.hasUsers" :startup-error="authState.error" />
  <div v-else-if="authState.ready" class="he-app-shell w-full bg-background text-ink font-sans relative overflow-hidden flex" :class="{ 'he-compact-shell': compact && !isEmbed, 'he-has-mini': audioPlaybackStore.state.media && !audioPlaybackStore.state.expanded }">
    <a href="#he-main-content" class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-accent focus:px-4 focus:py-3 focus:text-on-accent">跳转到主要内容</a>
    <div v-if="!isEmbed" class="he-ambient" aria-hidden="true"></div>
    <Sidebar v-if="!isEmbed && !compact" v-model:collapsed="desktopCollapsed" class="shrink-0 relative z-40" :user="authState.user" @logout="logout" />
    <main id="he-main-content" ref="mainScrollRef" :inert="audioPlaybackStore.state.expanded || !!route.query.media" tabindex="-1" @scroll="handleMainScroll" class="flex-1 min-w-0 relative z-10 box-border main-scroll-container focus:outline-none" :class="isEmbed ? 'overflow-hidden' : 'overflow-y-auto overflow-x-hidden custom-scrollbar'">
      <router-view v-slot="{ Component }"><transition name="page-fade" mode="out-in"><component :is="Component" /></transition></router-view>
      <div v-if="!isEmbed" class="h-8 w-full"></div>
    </main>
    <MobileNavigation v-if="compact && !isEmbed" :inert="audioPlaybackStore.state.expanded || !!route.query.media" /><GlobalAudioPlayer v-if="!isEmbed" /><AppUpdateNotice v-if="!isEmbed" />
    <button v-if="showBackToTop && !isEmbed && !route.query.media" type="button" @click="scrollToTop" class="he-back-top fixed right-6 z-30 size-11 rounded-full border border-line-strong bg-surface-3 text-muted shadow-pop flex items-center justify-center transition-colors duration-150 hover:text-ink focus-ring" aria-label="返回顶部"><ChevronUp :size="20" aria-hidden="true" /></button>
  </div>
  <div v-else class="he-app-shell bg-background text-subtle text-body flex items-center justify-center">正在检查登录状态</div>
</template>
<style>
.main-scroll-container {
  overscroll-behavior-y: contain;
}

/* The one ambient accent wash: static, behind everything, never animated. */
.he-ambient {
  position: fixed;
  inset: 0;
  z-index: 0;
  pointer-events: none;
  background: radial-gradient(1400px 700px at 20% -20%, rgb(var(--color-accent) / 0.07), rgb(var(--color-accent) / 0.025) 45%, transparent 80%);
}

.page-fade-enter-active {
  transition: opacity var(--duration-base) var(--ease-out), transform var(--duration-base) var(--ease-out);
}

.page-fade-leave-active {
  transition: opacity var(--duration-fast) ease-in;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(4px);
}

.page-fade-leave-to {
  opacity: 0;
}
</style>
