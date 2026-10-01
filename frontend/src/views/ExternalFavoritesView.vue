<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { Check, ChevronDown } from 'lucide-vue-next'
import wnacgLogo from '../assets/external-sources/wnacg.png'
import xLogo from '../assets/external-sources/x.svg'
import asmrOneLogo from '../assets/external-sources/asmr-one.png'
import pawchiveLogo from '../assets/external-sources/pawchive.png'
import { useRoute, useRouter } from 'vue-router'
import WnacgPanel from '../components/external/WnacgPanel.vue'
import XImportPanel from '../components/external/XImportPanel.vue'
import AsmrPanel from '../components/external/AsmrPanel.vue'
import PawchivePanel from '../components/external/pawchive/PawchivePanel.vue'

type SiteKey = 'wnacg' | 'x' | 'asmr' | 'pawchive'

interface SiteOption {
  key: SiteKey
  label: string
  description: string
  logo: string
}

const sites: SiteOption[] = [
  { key: 'wnacg', label: 'WNACG', description: '漫画收藏夹同步与下载', logo: wnacgLogo },
  { key: 'x', label: 'X (Twitter)', description: '喜欢媒体一键导入', logo: xLogo },
  { key: 'asmr', label: 'ASMR.one', description: 'ASMR 标记作品同步与下载', logo: asmrOneLogo },
  { key: 'pawchive', label: 'Pawchive', description: '作者收藏、帖子浏览与下载', logo: pawchiveLogo },
]

const route = useRoute()
const router = useRouter()
const activeSite = computed<SiteKey>(() => {
  const source = route.query.source
  return typeof source === 'string' && sites.some(site => site.key === source)
    ? source as SiteKey
    : 'wnacg'
})
const activeOption = computed(() => sites.find(site => site.key === activeSite.value) || sites[0]!)
const selectorRef = ref<HTMLDivElement | null>(null)
const selectorButtonRef = ref<HTMLButtonElement | null>(null)
const selectorOpen = ref(false)

const optionButtons = () => selectorRef.value?.querySelectorAll<HTMLButtonElement>('[data-source-option]')
const focusOption = (index: number) => { optionButtons()?.item(index)?.focus() }
const moveOptionFocus = (step: number) => {
  const buttons = optionButtons()
  if (!buttons?.length) return
  const current = Array.from(buttons).indexOf(document.activeElement as HTMLButtonElement)
  focusOption((current + step + buttons.length) % buttons.length)
}
const closeSelector = (restoreFocus = false) => {
  selectorOpen.value = false
  if (restoreFocus) void nextTick(() => selectorButtonRef.value?.focus())
}
const openSelector = () => {
  if (selectorOpen.value) return
  selectorOpen.value = true
  void nextTick(() => focusOption(sites.findIndex(site => site.key === activeSite.value)))
}
const toggleSelector = () => {
  if (selectorOpen.value) closeSelector(true)
  else openSelector()
}
const selectSite = (source: SiteKey, restoreFocus = true) => {
  closeSelector(restoreFocus)
  if (source !== activeSite.value) {
    void router.replace({ path: route.path, query: { ...route.query, source } })
  }
}
const onDocumentPointerDown = (event: PointerEvent) => {
  if (selectorOpen.value && !selectorRef.value?.contains(event.target as Node)) closeSelector()
}
const onDocumentFocusIn = (event: FocusEvent) => {
  if (selectorOpen.value && !selectorRef.value?.contains(event.target as Node)) closeSelector()
}
watch(() => route.query.source, () => { closeSelector(); try { localStorage.setItem('he_external_source', activeSite.value) } catch { /* optional */ } })
onMounted(() => {
  if (!route.query.source) {
    const saved = localStorage.getItem('he_external_source')
    if (saved && sites.some(site => site.key === saved)) void router.replace({ path: route.path, query: { ...route.query, source: saved } })
  }
  document.addEventListener('pointerdown', onDocumentPointerDown)
  document.addEventListener('focusin', onDocumentFocusIn)
})
onBeforeUnmount(() => {
  document.removeEventListener('pointerdown', onDocumentPointerDown)
  document.removeEventListener('focusin', onDocumentFocusIn)
})

</script>

<template>
  <div class="z-10 relative min-h-screen">
    <header class="he-page-header sticky top-0 z-40 bg-background/75 backdrop-blur-xl border-b border-white/10 px-6 md:px-8 py-5 mb-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-baseline gap-3">
          <h1 class="text-2xl md:text-3xl font-black text-white tracking-tight">外部收藏</h1>
          <p class="text-[11px] font-bold text-accent bg-accent/10 px-2 py-0.5 rounded-full border border-accent/20 uppercase tracking-widest">
            MULTI-SOURCE
          </p>
        </div>
        <div ref="selectorRef" class="relative w-full min-w-0 sm:w-72">
          <span class="mb-1.5 block text-[11px] font-bold uppercase tracking-wider text-white/50">数据源</span>
          <div class="relative sm:hidden">
            <div aria-hidden="true" class="flex min-h-14 w-full items-center gap-3 rounded-2xl border border-white/15 bg-sidebar/90 px-3 text-left shadow-sm">
              <span class="flex h-10 w-16 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-black/30">
                <img :src="activeOption.logo" alt="" draggable="false" class="object-contain" :class="activeSite === 'wnacg' ? 'w-14' : 'h-8 w-8'" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-bold text-white">{{ activeOption.label }}</span>
                <span class="block truncate text-xs text-white/55">{{ activeOption.description }}</span>
              </span>
              <ChevronDown :size="17" class="shrink-0 text-white/55" aria-hidden="true" />
            </div>
            <select
              :value="activeSite"
              aria-label="切换外部收藏数据源"
              class="absolute inset-0 z-10 h-full w-full cursor-pointer opacity-0"
              @change="selectSite(($event.target as HTMLSelectElement).value as SiteKey, false)"
            >
              <option v-for="site in sites" :key="site.key" :value="site.key">{{ site.label }}</option>
            </select>
          </div>
          <button
            ref="selectorButtonRef"
            type="button"
            :aria-expanded="selectorOpen"
            aria-controls="external-source-options"
            class="hidden sm:flex min-h-14 w-full items-center gap-3 rounded-2xl border bg-sidebar/90 px-3 text-left shadow-sm transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
            :class="selectorOpen ? 'border-accent/60 bg-accent/10' : 'border-white/15 hover:border-white/35 hover:bg-white/5'"
            @click="toggleSelector"
            @keydown.down.prevent="openSelector"
            @keydown.up.prevent="openSelector"
            @keydown.esc.prevent.stop="closeSelector(true)"
          >
            <span class="flex h-10 w-16 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-black/30">
              <img :src="activeOption.logo" alt="" draggable="false" class="object-contain" :class="activeSite === 'wnacg' ? 'w-14' : 'h-8 w-8'" />
            </span>
            <span class="min-w-0 flex-1">
              <span class="block truncate text-sm font-bold text-white">{{ activeOption.label }}</span>
              <span class="block truncate text-xs text-white/55">{{ activeOption.description }}</span>
            </span>
            <ChevronDown :size="17" class="shrink-0 text-white/55 transition-transform duration-200" :class="selectorOpen ? 'rotate-180' : ''" aria-hidden="true" />
          </button>
          <div
            v-show="selectorOpen"
            id="external-source-options"
            role="group"
            aria-label="可用数据源"
            class="hidden sm:block absolute right-0 top-[calc(100%+0.5rem)] z-50 w-full overflow-y-auto rounded-2xl border border-white/15 bg-sidebar p-2 shadow-2xl shadow-black/45 sm:w-80 max-h-[60vh]"
            @keydown.down.prevent="moveOptionFocus(1)"
            @keydown.up.prevent="moveOptionFocus(-1)"
            @keydown.home.prevent="focusOption(0)"
            @keydown.end.prevent="focusOption(sites.length - 1)"
            @keydown.esc.prevent.stop="closeSelector(true)"
          >
            <button
              v-for="site in sites"
              :key="site.key"
              data-source-option
              type="button"
              :aria-pressed="activeSite === site.key"
              class="flex min-h-16 w-full items-center gap-3 rounded-xl border px-3 py-2.5 text-left transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              :class="activeSite === site.key ? 'border-accent/35 bg-accent/12' : 'border-transparent hover:border-white/10 hover:bg-white/7'"
              @click="selectSite(site.key)"
            >
              <span class="flex h-10 w-16 shrink-0 items-center justify-center rounded-xl border border-white/10 bg-black/30">
                <img :src="site.logo" alt="" draggable="false" class="object-contain" :class="site.key === 'wnacg' ? 'w-14' : 'h-8 w-8'" />
              </span>
              <span class="min-w-0 flex-1">
                <span class="block truncate text-sm font-semibold text-white">{{ site.label }}</span>
                <span class="block text-xs leading-5 text-white/55">{{ site.description }}</span>
              </span>
              <Check v-if="activeSite === site.key" :size="17" class="shrink-0 text-accent" aria-hidden="true" />
            </button>
          </div>
        </div>
      </div>
    </header>

    <main class="px-6 md:px-8 pb-12 space-y-6">
      <!-- Keep panel instances alive so source state survives switching. -->
      <KeepAlive>
        <WnacgPanel v-if="activeSite === 'wnacg'" key="wnacg" />
        <XImportPanel v-else-if="activeSite === 'x'" key="x" />
        <AsmrPanel v-else-if="activeSite === 'asmr'" key="asmr" />
        <PawchivePanel v-else key="pawchive" />
      </KeepAlive>
    </main>
  </div>
</template>
