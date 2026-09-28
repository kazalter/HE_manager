<script setup lang="ts">
import { computed } from 'vue'
import { AtSign, ChevronDown, Globe2, Headphones } from 'lucide-vue-next'
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
  icon: any
}

const sites: SiteOption[] = [
  { key: 'wnacg', label: 'WNACG', description: '漫画收藏夹同步与下载', icon: Globe2 },
  { key: 'x', label: 'X (Twitter)', description: '喜欢媒体一键导入', icon: AtSign },
  { key: 'asmr', label: 'ASMR.one', description: 'ASMR 标记作品同步与下载', icon: Headphones },
  { key: 'pawchive', label: 'Pawchive', description: '作者收藏、帖子浏览与下载', icon: Globe2 },
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
const selectSite = (event: Event) => {
  const source = (event.target as HTMLSelectElement).value as SiteKey
  void router.replace({ path: route.path, query: { ...route.query, source } })
}

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
        <label class="grid w-full min-w-0 gap-1.5 sm:w-64">
          <span class="text-[11px] font-bold uppercase tracking-wider text-white/50">数据源</span>
          <span class="relative flex items-center">
            <component :is="activeOption.icon" :size="16" class="pointer-events-none absolute left-3 text-accent" aria-hidden="true" />
            <select
              :value="activeSite"
              class="min-h-11 w-full appearance-none rounded-xl border border-white/12 bg-sidebar/90 pl-10 pr-10 text-sm font-semibold text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
              @change="selectSite"
            >
              <option v-for="site in sites" :key="site.key" :value="site.key">{{ site.label }}</option>
            </select>
            <ChevronDown :size="16" class="pointer-events-none absolute right-3 text-white/55" aria-hidden="true" />
          </span>
          <span class="text-xs text-white/45">{{ activeOption.description }}</span>
        </label>
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
