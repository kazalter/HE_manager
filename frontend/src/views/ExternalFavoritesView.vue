<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import {
  ArrowRight,
  CheckCircle2,
  Layers,
  ShieldCheck,
} from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import wnacgLogo from '../assets/external-sources/wnacg.png'
import xLogo from '../assets/external-sources/x.svg'
import asmrOneLogo from '../assets/external-sources/asmr-one.png'
import pawchiveLogo from '../assets/external-sources/pawchive.png'
import WnacgPanel from '../components/external/WnacgPanel.vue'
import XImportPanel from '../components/external/XImportPanel.vue'
import AsmrPanel from '../components/external/AsmrPanel.vue'
import PawchivePanel from '../components/external/pawchive/PawchivePanel.vue'

type SiteKey = 'wnacg' | 'x' | 'asmr' | 'pawchive'

interface SiteOption {
  key: SiteKey
  label: string
  sublabel: string
  badge: string
  description: string
  logo: string
  logoClass?: string
  accentBorder: string
  accentBg: string
  accentText: string
  glowColor: string
  dotBg: string
}

const sites: SiteOption[] = [
  {
    key: 'wnacg',
    label: 'WNACG',
    sublabel: '绅士漫画',
    badge: 'MANGA',
    description: '个人收藏夹同步、章节目录解析与本地漫画库批量下载入库',
    logo: wnacgLogo,
    logoClass: 'w-14 object-contain',
    accentBorder: 'border-amber-500/50',
    accentBg: 'bg-amber-500/12',
    accentText: 'text-amber-300',
    glowColor: 'shadow-amber-500/15',
    dotBg: 'bg-amber-400',
  },
  {
    key: 'x',
    label: 'X (Twitter)',
    sublabel: '社交媒体',
    badge: 'MEDIA',
    description: '喜欢与书签媒体一键导入、推文归档与本地图片视频自动化转存',
    logo: xLogo,
    logoClass: 'h-7 w-7 object-contain',
    accentBorder: 'border-sky-500/50',
    accentBg: 'bg-sky-500/12',
    accentText: 'text-sky-300',
    glowColor: 'shadow-sky-500/15',
    dotBg: 'bg-sky-400',
  },
  {
    key: 'asmr',
    label: 'ASMR.one',
    sublabel: '同人音声',
    badge: 'AUDIO',
    description: '标记作品双向同步、沉浸式在线试听与智能格式过滤下载',
    logo: asmrOneLogo,
    logoClass: 'h-8 w-8 object-contain',
    accentBorder: 'border-purple-500/50',
    accentBg: 'bg-purple-500/12',
    accentText: 'text-purple-300',
    glowColor: 'shadow-purple-500/15',
    dotBg: 'bg-purple-400',
  },
  {
    key: 'pawchive',
    label: 'Pawchive',
    sublabel: '创作者画廊',
    badge: 'CREATOR',
    description: 'Patreon / Fanbox 创作者画廊订阅、高清序列播放与原图批量归档',
    logo: pawchiveLogo,
    logoClass: 'h-8 w-8 object-contain',
    accentBorder: 'border-pink-500/50',
    accentBg: 'bg-pink-500/12',
    accentText: 'text-pink-300',
    glowColor: 'shadow-pink-500/15',
    dotBg: 'bg-pink-400',
  },
]

const route = useRoute()
const router = useRouter()

const activeSite = computed<SiteKey>(() => {
  const source = route.query.source
  return typeof source === 'string' && sites.some(site => site.key === source)
    ? (source as SiteKey)
    : 'wnacg'
})

const activeOption = computed(() => sites.find(site => site.key === activeSite.value) || sites[0]!)

const selectSite = (source: SiteKey) => {
  if (source !== activeSite.value) {
    void router.replace({ path: route.path, query: { ...route.query, source } })
  }
}

watch(
  () => route.query.source,
  () => {
    try {
      localStorage.setItem('he_external_source', activeSite.value)
    } catch {
      /* ignore */
    }
  }
)

onMounted(() => {
  if (!route.query.source) {
    const saved = localStorage.getItem('he_external_source')
    if (saved && sites.some(site => site.key === saved)) {
      void router.replace({ path: route.path, query: { ...route.query, source: saved } })
    }
  }
})
</script>

<template>
  <div class="z-10 relative min-h-screen text-white pb-16">
    <!-- Top Sticky Header -->
    <header class="he-page-header sticky top-0 z-40 bg-surface/75 backdrop-blur-xl border-b border-white/10 px-4 md:px-8 py-3.5 mb-6">
      <div class="max-w-7xl mx-auto flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-3">
          <div class="w-10 h-10 rounded-2xl bg-gradient-to-tr from-accent/30 to-purple-500/20 border border-accent/40 flex items-center justify-center text-accent shrink-0 shadow-lg shadow-accent/10">
            <Layers :size="20" />
          </div>
          <div>
            <h1 class="text-xl md:text-2xl font-black text-white tracking-tight flex items-center gap-2">
              外部收藏与同步
            </h1>
            <p class="text-[11px] text-white/50 truncate">
              多平台收藏夹拉取 · 智能媒体转存 · 本地媒体库双向联动
            </p>
          </div>
        </div>

        <!-- Security & Status Badge -->
        <div class="flex items-center gap-2">
          <div class="flex items-center gap-1.5 px-3 py-1 rounded-full border border-emerald-400/25 bg-emerald-500/10 text-emerald-300 text-xs font-bold backdrop-blur-md">
            <ShieldCheck :size="14" />
            <span>凭据本地加密保护</span>
          </div>
        </div>
      </div>
    </header>

    <!-- Hero Source Switcher Cards -->
    <section class="max-w-7xl mx-auto px-4 md:px-8 mb-5">
      <div class="grid grid-cols-2 lg:grid-cols-4 gap-3 sm:gap-4">
        <button
          v-for="site in sites"
          :key="site.key"
          type="button"
          @click="selectSite(site.key)"
          :class="[
            activeSite === site.key
              ? `${site.accentBorder} ${site.accentBg} shadow-xl ${site.glowColor} ring-1 ring-white/15 scale-[1.01]`
              : 'border-white/10 bg-surface/40 hover:border-white/20 hover:bg-surface/70'
          ]"
          class="group relative flex flex-col justify-between p-4 rounded-2xl border transition-all duration-200 text-left active:scale-[0.98] cursor-pointer"
        >
          <div>
            <div class="flex items-start justify-between gap-2 mb-3">
              <!-- Logo Container -->
              <div class="h-10 w-16 flex items-center justify-center rounded-xl bg-black/40 border border-white/10 group-hover:scale-105 transition-transform duration-200">
                <img :src="site.logo" alt="" draggable="false" :class="site.logoClass || 'h-8 w-8 object-contain'" />
              </div>
              <!-- Badge -->
              <span
                :class="activeSite === site.key ? `${site.accentText} bg-white/10` : 'text-white/40 bg-white/5'"
                class="px-2 py-0.5 rounded-md text-[10px] font-black tracking-wider uppercase border border-white/5"
              >
                {{ site.badge }}
              </span>
            </div>

            <div class="flex items-center gap-1.5">
              <span class="text-sm sm:text-base font-black text-white group-hover:text-accent transition-colors">
                {{ site.label }}
              </span>
              <span class="text-xs text-white/40 font-medium">· {{ site.sublabel }}</span>
            </div>

            <p class="text-xs text-white/55 mt-1 line-clamp-1 leading-relaxed">
              {{ site.description }}
            </p>
          </div>

          <!-- Bottom Status Bar -->
          <div class="mt-3.5 pt-2.5 border-t border-white/8 flex items-center justify-between text-[11px]">
            <span
              :class="activeSite === site.key ? site.accentText : 'text-white/35'"
              class="font-bold flex items-center gap-1"
            >
              <CheckCircle2 v-if="activeSite === site.key" :size="12" />
              <span>{{ activeSite === site.key ? '当前数据源' : '点击切换' }}</span>
            </span>
            <ArrowRight
              :size="13"
              class="transition-transform group-hover:translate-x-1"
              :class="activeSite === site.key ? site.accentText : 'text-white/20'"
            />
          </div>
        </button>
      </div>
    </section>

    <!-- Active Platform Banner -->
    <div class="max-w-7xl mx-auto px-4 md:px-8 mb-5">
      <div class="flex items-center justify-between px-4 py-2.5 rounded-2xl border border-white/8 bg-white/[0.02] backdrop-blur-md">
        <div class="flex items-center gap-2.5 min-w-0">
          <!-- Pulsing Radar Indicator Light (Pixel-perfect aligned) -->
          <span class="relative flex h-2.5 w-2.5 shrink-0 items-center justify-center">
            <span
              class="absolute inline-flex h-full w-full animate-ping rounded-full opacity-75"
              :class="activeOption.dotBg"
            ></span>
            <span
              class="relative inline-flex h-2 w-2 rounded-full shadow-sm"
              :class="activeOption.dotBg"
            ></span>
          </span>
          <span class="text-xs font-bold text-white truncate">
            {{ activeOption.label }} 平台空间
          </span>
          <span class="hidden sm:inline text-xs text-white/40 truncate">
            — {{ activeOption.description }}
          </span>
        </div>
        <div class="flex items-center gap-2 shrink-0 text-xs text-white/45">
          <span class="hidden md:inline">定时自动同步已支持</span>
          <span class="px-2 py-0.5 rounded-md bg-white/5 border border-white/10 text-[10px] font-bold text-white/60">
            活跃
          </span>
        </div>
      </div>
    </div>

    <!-- Main Panel Container -->
    <main class="max-w-7xl mx-auto px-4 md:px-8 space-y-6">
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
