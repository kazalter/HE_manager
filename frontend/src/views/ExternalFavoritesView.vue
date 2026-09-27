<script setup lang="ts">
import { computed, ref } from 'vue'
import { AtSign, Globe2, Headphones } from 'lucide-vue-next'
import WnacgPanel from '../components/external/WnacgPanel.vue'
import XImportPanel from '../components/external/XImportPanel.vue'
import AsmrPanel from '../components/external/AsmrPanel.vue'

type SiteKey = 'wnacg' | 'x' | 'asmr'

interface SiteOption {
  key: SiteKey
  label: string
  description: string
  icon: any
  badge: string
}

const sites: SiteOption[] = [
  { key: 'wnacg', label: 'WNACG', description: '漫画收藏夹同步与下载', icon: Globe2, badge: 'Cookie 同步' },
  { key: 'x', label: 'X (Twitter)', description: '喜欢媒体一键导入', icon: AtSign, badge: '归档导入' },
  { key: 'asmr', label: 'ASMR.one', description: 'ASMR 标记作品同步与下载', icon: Headphones, badge: 'Token 同步' },
]

const activeSite = ref<SiteKey>('wnacg')

const activeOption = computed(() => sites.find(site => site.key === activeSite.value) || sites[0])

const selectSite = (key: SiteKey) => {
  activeSite.value = key
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
        <p class="text-xs text-white/45">
          当前数据源：<span class="text-white/85 font-bold">{{ activeOption.label }}</span>
        </p>
      </div>
    </header>

    <main class="px-6 md:px-8 pb-12 space-y-6">
      <!-- Source segmented tabs (flat, 1-click) -->
      <section class="grid grid-cols-1 sm:grid-cols-3 gap-3.5">
        <button
          v-for="site in sites"
          :key="site.key"
          type="button"
          @click="selectSite(site.key)"
          :class="activeSite === site.key
            ? 'border-accent bg-accent/15 ring-1 ring-accent/30 shadow-lg shadow-accent/5'
            : 'border-white/10 bg-white/[0.03] hover:border-white/20 hover:bg-white/[0.06]'"
          class="group relative text-left rounded-2xl border p-4 transition-all duration-200 flex items-center gap-3.5 cursor-pointer"
        >
          <div
            :class="activeSite === site.key ? 'bg-accent text-white shadow-md shadow-accent/20' : 'bg-white/5 border border-white/10 text-white/70 group-hover:text-white'"
            class="w-11 h-11 rounded-xl flex items-center justify-center shrink-0 transition-all"
          >
            <component :is="site.icon" :size="20" />
          </div>
          <div class="min-w-0 flex-1">
            <div class="flex items-center gap-2">
              <span class="text-sm font-black text-white truncate">{{ site.label }}</span>
              <span
                :class="activeSite === site.key ? 'bg-accent/25 text-accent border-accent/40' : 'bg-white/5 text-white/45 border-white/10'"
                class="text-[10px] font-bold border rounded-md px-1.5 py-0.5 tracking-wider uppercase shrink-0"
              >
                {{ site.badge }}
              </span>
            </div>
            <p class="text-xs text-white/50 mt-0.5 truncate">{{ site.description }}</p>
          </div>
          <div v-if="activeSite === site.key" class="w-2 h-2 rounded-full bg-accent shrink-0 ring-4 ring-accent/20"></div>
        </button>
      </section>

      <!-- Active panel; keep-alive so panel state survives switching tabs -->
      <KeepAlive>
        <WnacgPanel v-if="activeSite === 'wnacg'" key="wnacg" />
        <XImportPanel v-else-if="activeSite === 'x'" key="x" />
        <AsmrPanel v-else-if="activeSite === 'asmr'" key="asmr" />
      </KeepAlive>
    </main>
  </div>
</template>
