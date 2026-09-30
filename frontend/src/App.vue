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
const compact = useCompactViewport()
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
  <div v-else-if="authState.ready" class="he-app-shell w-full bg-background text-white/90 font-sans selection:bg-accent selection:text-white relative overflow-hidden flex" :class="{ 'he-compact-shell': compact && !isEmbed, 'he-has-mini': audioPlaybackStore.state.media && !audioPlaybackStore.state.expanded }">
    <a href="#he-main-content" class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-accent focus:px-4 focus:py-3 focus:text-white">跳转到主要内容</a>
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0" aria-hidden="true"><div class="glow-sphere sphere-1"></div><div class="glow-sphere sphere-2"></div><div class="glow-sphere sphere-3"></div></div>
    <Sidebar v-if="!isEmbed && !compact" v-model:collapsed="desktopCollapsed" class="shrink-0 relative z-40" :user="authState.user" @logout="logout" />
    <main id="he-main-content" ref="mainScrollRef" :inert="audioPlaybackStore.state.expanded || !!route.query.media" tabindex="-1" @scroll="handleMainScroll" class="flex-1 min-w-0 relative z-10 box-border main-scroll-container" :class="isEmbed ? 'overflow-hidden' : 'overflow-y-auto overflow-x-hidden custom-scrollbar'">
      <router-view v-slot="{ Component }"><transition name="page-fade" mode="out-in"><component :is="Component" /></transition></router-view>
      <div v-if="!isEmbed" class="h-8 w-full"></div>
    </main>
    <MobileNavigation v-if="compact && !isEmbed" :inert="audioPlaybackStore.state.expanded || !!route.query.media" /><GlobalAudioPlayer v-if="!isEmbed" /><AppUpdateNotice v-if="!isEmbed" />
    <button v-if="showBackToTop && !isEmbed && !route.query.media" type="button" @click="scrollToTop" class="he-back-top fixed right-4 z-30 w-11 h-11 rounded-2xl bg-sidebar/95 border border-white/20 flex items-center justify-center focus-visible:ring-2 focus-visible:ring-accent" aria-label="返回顶部"><ChevronUp :size="20" aria-hidden="true" /></button>
  </div>
  <div v-else class="he-app-shell bg-background text-white/60 flex items-center justify-center">正在检查登录状态</div>
</template>
<style>
.main-scroll-container {
  overscroll-behavior-y: contain;
}

.glow-sphere {
  position: absolute;
  border-radius: 50%;
  filter: blur(90px);
  opacity: 0.09;
  pointer-events: none;
  will-change: transform;
  backface-visibility: hidden;
  transform: translate3d(0, 0, 0);
}

.sphere-1 {
  top: -20%;
  left: -10%;
  width: 60%;
  height: 60%;
  background: radial-gradient(circle, rgba(var(--color-accent), 0.85) 0%, transparent 70%);
  animation: float-slow 25s infinite alternate ease-in-out;
}

.sphere-2 {
  bottom: -15%;
  right: -10%;
  width: 55%;
  height: 55%;
  background: radial-gradient(circle, rgba(139, 92, 246, 0.85) 0%, transparent 70%);
  animation: float-slow-reverse 20s infinite alternate ease-in-out;
}

.sphere-3 {
  top: 30%;
  right: 15%;
  width: 40%;
  height: 40%;
  background: radial-gradient(circle, rgba(6, 182, 212, 0.85) 0%, transparent 70%);
  animation: float-slow-alt 30s infinite alternate ease-in-out;
}

@keyframes float-slow {
  0% { transform: translate3d(0, 0, 0) scale(1); }
  50% { transform: translate3d(8%, 5%, 0) scale(1.15); }
  100% { transform: translate3d(-5%, -8%, 0) scale(0.9); }
}

@keyframes float-slow-reverse {
  0% { transform: translate3d(0, 0, 0) scale(0.9); }
  50% { transform: translate3d(-10%, 8%, 0) scale(1.1); }
  100% { transform: translate3d(5%, -5%, 0) scale(1); }
}

@keyframes float-slow-alt {
  0% { transform: translate3d(0, 0, 0) rotate(0deg); }
  50% { transform: translate3d(6%, -10%, 0) rotate(180deg); }
  100% { transform: translate3d(-8%, 6%, 0) rotate(360deg); }
}

.page-fade-enter-active,
.page-fade-leave-active {
  transition: all 0.25s cubic-bezier(0.4, 0, 0.2, 1);
  will-change: transform, opacity;
}

.page-fade-enter-from {
  opacity: 0;
  transform: translateY(12px) scale(0.995);
}

.page-fade-leave-to {
  opacity: 0;
  transform: translateY(-12px) scale(0.995);
}

@media (max-width: 1100px) {
  .sphere-3 {
    display: none;
  }
}

@media (max-width: 700px), (prefers-reduced-motion: reduce) {
  .glow-sphere {
    filter: blur(70px);
    opacity: 0.06;
    animation: none !important;
  }

  .page-fade-enter-active,
  .page-fade-leave-active {
    transition-duration: 0.15s;
  }
}

.custom-scrollbar::-webkit-scrollbar {
  width: 6px;
}

.custom-scrollbar::-webkit-scrollbar-track {
  background: transparent;
}

.custom-scrollbar::-webkit-scrollbar-thumb {
  background: rgba(255, 255, 255, 0.12);
  border-radius: 10px;
}

.custom-scrollbar::-webkit-scrollbar-thumb:hover {
  background: rgba(255, 255, 255, 0.22);
}
</style>
