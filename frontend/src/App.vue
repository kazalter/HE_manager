<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue'
import { useRoute } from 'vue-router'
import { authState, logout } from './auth'
import { ChevronUp, Menu } from 'lucide-vue-next'
import Sidebar from './components/Sidebar.vue'
import AuthView from './views/AuthView.vue'

const desktopCollapsed = ref(localStorage.getItem('he_sidebar_collapsed') === 'true')
const isCompactViewport = ref(false)
const mobileSidebarOpen = ref(false)
const menuTriggerRef = ref<HTMLButtonElement | null>(null)

const isCollapsed = computed({
  get: () => isCompactViewport.value ? !mobileSidebarOpen.value : desktopCollapsed.value,
  set: (value: boolean) => {
    if (isCompactViewport.value) {
      mobileSidebarOpen.value = !value
    } else {
      desktopCollapsed.value = value
    }
  },
})

watch(desktopCollapsed, (newVal) => {
  localStorage.setItem('he_sidebar_collapsed', String(newVal))
})

const route = useRoute()
const mainScrollRef = ref<HTMLElement | null>(null)
const showBackToTop = ref(false)

const updateResponsiveShell = () => {
  const nextCompact = window.innerWidth < 900
  if (nextCompact && !isCompactViewport.value) mobileSidebarOpen.value = false
  isCompactViewport.value = nextCompact
}

watch(() => route.fullPath, () => {
  if (isCompactViewport.value) mobileSidebarOpen.value = false
})

watch(mobileSidebarOpen, async (open) => {
  if (!isCompactViewport.value) return
  await nextTick()
  if (open) {
    document.querySelector<HTMLButtonElement>('#he-sidebar [data-mobile-close]')?.focus()
  } else {
    menuTriggerRef.value?.focus()
  }
})

const handleMenuKeydown = (event: KeyboardEvent) => {
  if (!isCompactViewport.value || !mobileSidebarOpen.value) return
  if (event.key === 'Escape') {
    event.preventDefault()
    mobileSidebarOpen.value = false
    return
  }
  if (event.key !== 'Tab') return

  const sidebar = document.getElementById('he-sidebar')
  const focusable = sidebar?.querySelectorAll<HTMLElement>('a[href], button:not([disabled])')
  if (!focusable?.length) return
  const first = focusable[0]!
  const last = focusable[focusable.length - 1]!
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault()
    last.focus()
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault()
    first.focus()
  }
}

watch(() => route.path, () => {
  if (mainScrollRef.value) {
    mainScrollRef.value.scrollTo({ top: 0, behavior: 'instant' as ScrollBehavior })
    mainScrollRef.value.scrollTop = 0
  }
  showBackToTop.value = false
})

const handleMainScroll = (event: Event) => {
  const target = event.target as HTMLElement
  showBackToTop.value = target.scrollTop > 360
}

const scrollToTop = () => {
  if (mainScrollRef.value) {
    mainScrollRef.value.scrollTo({ top: 0, behavior: 'smooth' })
  }
}

onMounted(() => {
  updateResponsiveShell()
  window.addEventListener('resize', updateResponsiveShell, { passive: true })
  window.addEventListener('keydown', handleMenuKeydown)
})

onUnmounted(() => {
  window.removeEventListener('resize', updateResponsiveShell)
  window.removeEventListener('keydown', handleMenuKeydown)
})

const isEmbed = computed(() => {
  return route.path.endsWith('/embed') || route.query.embed === 'true'
})
const mobileMenuOpen = computed(() => isCompactViewport.value && mobileSidebarOpen.value && !isEmbed.value)
</script>

<template>
  <AuthView v-if="authState.ready && !authState.user" :has-users="authState.hasUsers" :startup-error="authState.error" />
  <div
    v-else-if="authState.ready"
    class="h-screen w-full bg-background text-white/90 font-sans selection:bg-accent selection:text-white relative overflow-hidden flex"
  >
    <a
      v-if="!mobileMenuOpen"
      href="#he-main-content"
      class="sr-only focus:not-sr-only focus:fixed focus:left-4 focus:top-4 focus:z-[60] focus:rounded-lg focus:bg-accent focus:px-4 focus:py-3 focus:text-white focus:ring-2 focus:ring-white"
    >跳转到主要内容</a>
    <!-- Apple-style Dynamic Ambient Glow -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <div class="glow-sphere sphere-1"></div>
      <div class="glow-sphere sphere-2"></div>
      <div class="glow-sphere sphere-3"></div>
    </div>

    <Sidebar
      v-if="!isEmbed"
      id="he-sidebar"
      v-model:collapsed="isCollapsed"
      :is-compact="isCompactViewport"
      :inert="isCompactViewport && isCollapsed"
      :aria-hidden="isCompactViewport && isCollapsed ? 'true' : undefined"
      :class="isCompactViewport ? 'fixed left-0 top-0 z-50' : 'shrink-0 relative z-40'"
      class="transition-all duration-300 ease-in-out"
      :user="authState.user"
      @logout="logout"
    />

    <!-- Mobile Drawer Overlay Backdrop -->
    <div
      v-if="mobileMenuOpen"
      class="fixed inset-0 z-40 bg-black/60 backdrop-blur-sm cursor-default transition-opacity"
      aria-hidden="true"
      @click="isCollapsed = true"
    ></div>

    <!-- Mobile Hamburger Trigger (Only on compact screen when collapsed) -->
    <button
      v-if="isCompactViewport && isCollapsed && !isEmbed"
      ref="menuTriggerRef"
      type="button"
      @click="isCollapsed = false"
      class="fixed z-50 left-4 top-4 w-11 h-11 rounded-xl border border-white/15 bg-sidebar/85 backdrop-blur-xl flex items-center justify-center text-white shadow-md shadow-accent/20 transition-all duration-200 cursor-pointer hover:bg-white/10 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
      title="展开侧边栏"
      aria-label="展开侧边栏"
      aria-controls="he-sidebar"
      :aria-expanded="mobileMenuOpen"
    >
      <Menu :size="20" />
    </button>

    <main
      id="he-main-content"
      ref="mainScrollRef"
      tabindex="-1"
      :inert="mobileMenuOpen"
      @scroll="handleMainScroll"
      class="flex-1 min-w-0 relative z-10 box-border main-scroll-container"
      :class="isEmbed ? 'h-screen overflow-hidden' : 'h-screen overflow-y-auto overflow-x-hidden scroll-smooth custom-scrollbar'"
    >
      <router-view v-slot="{ Component }">
        <transition name="page-fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
      <div v-if="!isEmbed" class="h-20 w-full"></div>
    </main>

    <!-- Smooth Back To Top Floating Action Button -->
    <transition name="page-fade">
      <button
        v-if="showBackToTop && !isEmbed && !mobileMenuOpen"
        type="button"
        @click="scrollToTop"
        class="fixed bottom-7 right-7 z-40 w-11 h-11 rounded-2xl bg-sidebar/85 hover:bg-accent backdrop-blur-2xl border border-white/15 text-white/70 hover:text-white shadow-2xl shadow-black/60 flex items-center justify-center transition-all duration-300 hover:scale-105 active:scale-95 cursor-pointer"
        title="返回顶部"
        aria-label="返回顶部"
      >
        <ChevronUp :size="20" />
      </button>
    </transition>
  </div>
  <div v-else class="h-screen w-full bg-background text-white/50 flex items-center justify-center">
    正在检查登录状态
  </div>
</template>

<style>
.main-scroll-container {
  contain: paint;
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
