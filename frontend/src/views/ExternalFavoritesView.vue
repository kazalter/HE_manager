<script setup lang="ts">
import { computed, onMounted, watch } from 'vue'
import { AtSign, BookOpen, Headphones, PawPrint } from 'lucide-vue-next'
import { useRoute, useRouter } from 'vue-router'
import { PageHeader, UiSegmented, type SegmentedOption } from '../components/ui'
import WnacgPanel from '../components/external/WnacgPanel.vue'
import XImportPanel from '../components/external/XImportPanel.vue'
import AsmrPanel from '../components/external/AsmrPanel.vue'
import PawchivePanel from '../components/external/pawchive/PawchivePanel.vue'

type SiteKey = 'wnacg' | 'x' | 'asmr' | 'pawchive'

// Sources get one neutral icon each; the theme accent only marks the active one.
const sites: (SegmentedOption<SiteKey> & { description: string })[] = [
  { value: 'wnacg', label: 'WNACG', icon: BookOpen, description: '同步 WNACG 收藏夹，批量下载漫画入库' },
  { value: 'x', label: 'X', icon: AtSign, description: '导入 X 喜欢的帖子，转存图片与视频' },
  { value: 'asmr', label: 'ASMR', icon: Headphones, description: '同步 asmr.one 喜欢列表，按格式筛选下载音声' },
  { value: 'pawchive', label: 'Pawchive', icon: PawPrint, description: '浏览收藏的 Patreon / Fanbox 作者，归档原图' },
]

const route = useRoute()
const router = useRouter()

const activeSite = computed<SiteKey>(() => {
  const source = route.query.source
  return typeof source === 'string' && sites.some(site => site.value === source)
    ? (source as SiteKey)
    : 'wnacg'
})

const activeOption = computed(() => sites.find(site => site.value === activeSite.value) || sites[0]!)

const selectSite = (source: SiteKey) => {
  if (source !== activeSite.value) {
    void router.replace({ path: route.path, query: { ...route.query, source } })
  }
}

const siteModel = computed<SiteKey>({
  get: () => activeSite.value,
  set: selectSite,
})

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
    if (saved && sites.some(site => site.value === saved)) {
      void router.replace({ path: route.path, query: { ...route.query, source: saved } })
    }
  }
})
</script>

<template>
  <div class="min-h-full">
    <PageHeader title="外部收藏" :description="activeOption.description">
      <div class="he-source-switch max-w-full sm:max-w-md">
        <UiSegmented v-model="siteModel" label="数据源" :options="sites" block />
      </div>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container">
        <!-- Keep panel instances alive so source state survives switching. -->
        <KeepAlive>
          <WnacgPanel v-if="activeSite === 'wnacg'" key="wnacg" />
          <XImportPanel v-else-if="activeSite === 'x'" key="x" />
          <AsmrPanel v-else-if="activeSite === 'asmr'" key="asmr" />
          <PawchivePanel v-else key="pawchive" />
        </KeepAlive>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Phones: four labels fit only without the icons. */
@media (max-width: 639px) {
  .he-source-switch :deep([role='radio'] svg) {
    display: none;
  }
  .he-source-switch :deep([role='radio']) {
    padding-inline: 4px;
  }
}

/* Touch: the switcher is the page's main navigation, give it a 40px target. */
@media (pointer: coarse) {
  .he-source-switch :deep([role='radio']) {
    height: 2.5rem;
  }
}
</style>
