<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { AlertTriangle, ArrowLeft, ExternalLink, Palette, Search, X } from 'lucide-vue-next'
import { API_BASE_URL, thumbnailUrl } from '../config'
import type { Creator, CreatorDetail, Media } from '../types'
import MediaCard from '../components/MediaCard.vue'
import { AsyncMediaDetail as MediaDetail } from '../components/asyncComponents'
import { EmptyState, PageHeader, UiButton, UiChip, UiIconButton, UiInput, UiSegmented, UiSkeleton } from '../components/ui'

const route = useRoute()
const router = useRouter()

const screenName = computed(() => (route.params.screenName as string) || '')
const isDetail = computed(() => screenName.value.length > 0)

// ---- list mode ----
const creators = ref<Creator[]>([])
const listLoading = ref(true)
const search = ref('')
const sortBy = ref<'count' | 'name' | 'pending'>('count')

const fetchCreators = async () => {
  listLoading.value = true
  try {
    const res = await axios.get<Creator[]>(`${API_BASE_URL}/creators`, {
      params: { search: search.value || undefined, sort: sortBy.value },
    })
    creators.value = res.data
  } catch (err) {
    console.error('Failed to fetch creators:', err)
    creators.value = []
  } finally {
    listLoading.value = false
  }
}

let searchTimer: number | undefined
watch(search, () => {
  window.clearTimeout(searchTimer)
  searchTimer = window.setTimeout(fetchCreators, 250)
})
watch(sortBy, fetchCreators)

const openCreator = (sn: string) => {
  router.push({ name: 'creator-detail', params: { screenName: sn } })
}

const selectedLetter = ref<string>('ALL')

const availableLetters = computed(() => {
  const set = new Set<string>()
  for (const c of creators.value) {
    const raw = (c.display_name || c.screen_name || '').trim()
    const firstChar = raw[0]?.toUpperCase()
    if (firstChar && firstChar >= 'A' && firstChar <= 'Z') {
      set.add(firstChar)
    } else if (firstChar) {
      set.add('#')
    }
  }
  const alphabet = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'.split('').filter(l => set.has(l))
  if (set.has('#')) alphabet.push('#')
  return ['ALL', ...alphabet]
})

const displayedCreators = computed(() => {
  if (selectedLetter.value === 'ALL') return creators.value
  return creators.value.filter(c => {
    const raw = (c.display_name || c.screen_name || '').trim()
    const firstChar = raw[0]?.toUpperCase()
    if (selectedLetter.value === '#') {
      return !firstChar || firstChar < 'A' || firstChar > 'Z'
    }
    return firstChar === selectedLetter.value
  })
})

// ---- detail mode ----
const detail = ref<CreatorDetail | null>(null)
const detailLoading = ref(false)
const detailError = ref('')
const selectedMedia = ref<Media | null>(null)
const detailTypeFilter = ref<string>('all')
const detailSort = ref<'desc' | 'asc' | 'rating' | 'title'>('desc')

const handleBack = () => {
  if (window.history.state?.back) {
    router.back()
  } else {
    router.push({ name: 'creators' })
  }
}

const detailMedia = computed(() => detail.value?.media ?? [])

const mediaTypesInDetail = computed(() => {
  const counts: Record<string, number> = {}
  for (const m of detailMedia.value) {
    counts[m.media_type] = (counts[m.media_type] || 0) + 1
  }
  return counts
})

const filteredDetailMedia = computed(() => {
  let list = detailMedia.value
  if (detailTypeFilter.value !== 'all') {
    list = list.filter(m => m.media_type === detailTypeFilter.value)
  }
  const sorted = [...list]
  if (detailSort.value === 'asc') {
    sorted.sort((a, b) => new Date(a.created_at).getTime() - new Date(b.created_at).getTime())
  } else if (detailSort.value === 'rating') {
    sorted.sort((a, b) => (b.rating ?? 0) - (a.rating ?? 0))
  } else if (detailSort.value === 'title') {
    sorted.sort((a, b) => a.title.localeCompare(b.title))
  } else {
    sorted.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())
  }
  return sorted
})

const fetchDetail = async (sn: string) => {
  detailLoading.value = true
  detailError.value = ''
  try {
    const res = await axios.get<CreatorDetail>(`${API_BASE_URL}/creators/${encodeURIComponent(sn)}`)
    detail.value = res.data
  } catch (err: any) {
    detailError.value = err?.response?.status === 404
      ? '该创作者没有已入库的作品。'
      : '加载创作者作品失败。'
    detail.value = null
  } finally {
    detailLoading.value = false
  }
}

// Reuse HomeView's ?media= modal mechanism so MediaDetail works identically here.
const openMedia = (media: Media, replace = false) => {
  selectedMedia.value = media
  const location = { path: route.path, query: { ...route.query, media: String(media.id) } }
  replace ? router.replace(location) : router.push(location)
}

const closeMedia = () => {
  selectedMedia.value = null
  const query = { ...route.query }
  delete query.media
  router.push({ path: route.path, query })
}

const syncSelectedMediaFromRoute = async () => {
  const mediaId = Number(route.query.media)
  if (!mediaId) {
    selectedMedia.value = null
    return
  }
  if (selectedMedia.value?.id === mediaId) return
  const local = detailMedia.value.find(m => m.id === mediaId)
  if (local) {
    selectedMedia.value = local
    return
  }
  try {
    const res = await axios.get(`${API_BASE_URL}/media/${mediaId}`)
    selectedMedia.value = res.data
  } catch (err) {
    console.error('Failed to fetch selected media:', err)
  }
}

const updateMediaInList = (media: Media) => {
  if (!detail.value) return
  const i = detail.value.media.findIndex(m => m.id === media.id)
  if (i >= 0) detail.value.media[i] = media
  if (selectedMedia.value?.id === media.id) selectedMedia.value = media
}

// True only while we are still inside the creators section. When the user
// navigates away (e.g. to /stats), the route changes and screenName drops to
// '', which would otherwise flip isDetail + refetch on the *leaving* component
// mid-transition and lock up the <transition mode="out-in">, leaving a blank
// page until a full reload. Guarding here keeps the leaving view static.
const onCreatorsRoute = () => route.name === 'creators' || route.name === 'creator-detail'

watch(screenName, async (sn) => {
  if (!onCreatorsRoute()) return
  if (sn) {
    await fetchDetail(sn)
    await syncSelectedMediaFromRoute()
  } else {
    detail.value = null
    selectedMedia.value = null
    fetchCreators()
  }
})
watch(() => route.query.media, () => {
  if (!onCreatorsRoute()) return
  syncSelectedMediaFromRoute()
})

onMounted(async () => {
  if (isDetail.value) {
    await fetchDetail(screenName.value)
    await syncSelectedMediaFromRoute()
  } else {
    fetchCreators()
  }
})

const displayName = (c: Creator) => c.display_name || `@${c.screen_name}`
const sortOptions = [
  { value: 'count' as const, label: '作品数' },
  { value: 'pending' as const, label: '待入库' },
  { value: 'name' as const, label: '名称' },
]
const detailSortOptions = [
  { value: 'desc' as const, label: '最新' },
  { value: 'asc' as const, label: '最早' },
  { value: 'rating' as const, label: '评分' },
  { value: 'title' as const, label: '标题' },
]
const detailTypeOptions = computed(() => [
  { k: 'all', label: '全部', count: detailMedia.value.length },
  { k: 'image', label: '杂图', count: mediaTypesInDetail.value['image'] || 0 },
  { k: 'manga', label: '漫画', count: mediaTypesInDetail.value['manga'] || 0 },
  { k: 'video', label: '视频', count: mediaTypesInDetail.value['video'] || 0 },
  { k: 'audio', label: '音频', count: mediaTypesInDetail.value['audio'] || 0 },
].filter(x => x.k === 'all' || x.count > 0))
const detailIsX = computed(() => !detail.value || detail.value.creator.kind === 'x')
const xProfileUrl = (sn: string) => `https://x.com/${sn}`
</script>

<template>
  <div class="relative min-h-full">
  <!-- Single root element above: <transition mode="out-in"> in App.vue cannot
       drive a multi-root component. Keep this <div> the sole root node — no
       sibling comments at <template> root, since in dev mode Vue keeps comment
       vnodes and they would re-introduce the multi-root blank-page bug. -->
  <!-- ===== list mode ===== -->
  <div v-if="!isDetail">
    <PageHeader title="创作者" :count="`${creators.length} 位`" description="按作者聚合 X 收藏和漫画作品">
      <div class="flex flex-col gap-3 sm:flex-row sm:items-center">
        <UiInput v-model="search" type="search" placeholder="搜索作者名 / @用户名…" aria-label="搜索作者名或用户名" class="w-full sm:w-80">
          <template #leading><Search :size="16" /></template>
          <template #trailing><UiIconButton v-if="search" label="清除搜索" size="sm" @click="search = ''"><X :size="14" /></UiIconButton></template>
        </UiInput>
        <UiSegmented v-model="sortBy" label="排序方式" :options="sortOptions" class="self-start sm:self-auto" />
      </div>
      <div
        v-if="availableLetters.length > 2"
        class="scrollbar-none -mx-4 mt-3 flex gap-2 overflow-x-auto px-4 sm:-mx-6 sm:px-6 lg:mx-0 lg:flex-wrap lg:px-0"
        role="group"
        aria-label="按首字母筛选"
      >
        <UiChip
          v-for="l in availableLetters"
          :key="l"
          size="sm"
          :selected="selectedLetter === l"
          class="min-w-8 justify-center pointer-coarse:h-10 pointer-coarse:min-w-10"
          @click="selectedLetter = l"
        >{{ l === 'ALL' ? '全部' : l }}</UiChip>
      </div>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container">
        <div v-if="listLoading" class="poster-grid" aria-busy="true">
          <div v-for="i in 12" :key="i">
            <UiSkeleton class="aspect-[3/4] w-full rounded-2xl" />
            <UiSkeleton shape="text" class="mt-2.5 h-[0.85em] w-4/5" />
            <UiSkeleton shape="text" class="mt-1.5 h-[0.85em] w-1/2" />
          </div>
        </div>

        <div v-else-if="displayedCreators.length > 0" class="poster-grid">
          <button
            v-for="c in displayedCreators"
            :key="c.key"
            type="button"
            :disabled="!c.screen_name"
            class="group flex flex-col rounded-2xl text-left focus-ring enabled:cursor-pointer disabled:cursor-default"
            @click="c.screen_name && openCreator(c.screen_name)"
          >
            <div class="relative aspect-[3/4] overflow-hidden rounded-2xl bg-surface-2">
              <img
                v-if="c.cover_path"
                :src="thumbnailUrl(c.cover_path)"
                :alt="displayName(c)"
                class="absolute inset-0 h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.03]"
                loading="eager"
                decoding="async"
              />
              <div v-else class="grid h-full w-full place-items-center text-faint">
                <Palette :size="36" aria-hidden="true" />
              </div>
              <div class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/8 transition-colors group-hover:ring-white/20"></div>
              <span
                v-if="c.posts_pending > 0"
                class="absolute top-2 right-2 inline-flex h-6 items-center gap-1 rounded-md bg-black/60 px-1.5 text-caption font-medium text-white/90 tabular-nums"
                :title="`还有 ${c.posts_pending} 条已知推文未入库`"
              >+{{ c.posts_pending }} 待入库</span>
            </div>
            <div class="mt-2.5 min-w-0 px-0.5">
              <h3 class="truncate text-body font-medium text-ink" :title="displayName(c)">{{ displayName(c) }}</h3>
              <p class="mt-0.5 truncate text-meta text-subtle">{{ c.kind === 'x' && c.screen_name ? `@${c.screen_name}` : '漫画作者' }}</p>
              <p class="mt-0.5 text-caption text-subtle tabular-nums">
                {{ c.media_count }} 件作品<template v-if="c.kind === 'x' && c.posts_known > 0"><span class="text-faint" aria-hidden="true"> · </span>{{ c.posts_known }} 推</template>
              </p>
            </div>
          </button>
        </div>

        <EmptyState v-else-if="creators.length > 0" :icon="Search" :title="`首字母「${selectedLetter}」下暂无创作者`">
          <UiButton variant="secondary" size="sm" @click="selectedLetter = 'ALL'">查看全部创作者</UiButton>
        </EmptyState>

        <EmptyState v-else :icon="Palette" title="还没有可聚合的创作者" description="导入一些 X（推特）喜欢后，作者会自动出现在这里。" />
      </div>
    </div>
  </div>

  <!-- ===== detail mode ===== -->
  <div v-else>
    <PageHeader :title="detail?.creator.display_name || '@' + screenName">
      <template #leading>
        <UiIconButton label="返回创作者列表" variant="secondary" @click="handleBack"><ArrowLeft :size="18" /></UiIconButton>
      </template>
      <template #description>
        <span class="flex flex-wrap items-center gap-x-1.5 gap-y-0.5 tabular-nums">
          <a
            v-if="detailIsX"
            :href="xProfileUrl(screenName)"
            target="_blank"
            rel="noopener"
            class="inline-flex items-center gap-1 rounded-sm whitespace-nowrap text-muted transition-colors hover:text-ink focus-ring"
          >@{{ screenName }} <ExternalLink :size="12" aria-hidden="true" /></a>
          <span v-else class="whitespace-nowrap">漫画作者</span>
          <template v-if="detail">
            <span class="text-faint" aria-hidden="true">·</span>
            <span class="whitespace-nowrap">{{ detail.creator.media_count }} 件作品</span>
          </template>
          <template v-if="detail && detail.creator.posts_pending > 0">
            <span class="text-faint" aria-hidden="true">·</span>
            <span class="whitespace-nowrap">{{ detail.creator.posts_pending }} 条推文待入库</span>
          </template>
        </span>
      </template>
      <div class="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div class="scrollbar-none -mx-4 flex gap-2 overflow-x-auto px-4 sm:-mx-6 sm:px-6 md:mx-0 md:px-0" role="group" aria-label="按类型筛选">
          <UiChip
            v-for="t in detailTypeOptions"
            :key="t.k"
            :selected="detailTypeFilter === t.k"
            :count="t.count"
            @click="detailTypeFilter = t.k"
          >{{ t.label }}</UiChip>
        </div>
        <UiSegmented v-model="detailSort" label="排序方式" :options="detailSortOptions" class="self-start md:self-auto" />
      </div>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container">
        <div v-if="detailLoading" class="poster-grid" aria-busy="true">
          <div v-for="i in 12" :key="i">
            <UiSkeleton class="aspect-[2/3] w-full rounded-2xl" />
            <UiSkeleton shape="text" class="mt-2.5 h-[0.85em] w-4/5" />
            <UiSkeleton shape="text" class="mt-1.5 h-[0.85em] w-1/2" />
          </div>
        </div>

        <EmptyState v-else-if="detailError" tone="danger" :icon="AlertTriangle" :title="detailError">
          <UiButton variant="secondary" size="sm" @click="handleBack"><template #icon><ArrowLeft :size="14" /></template>返回创作者列表</UiButton>
        </EmptyState>

        <EmptyState v-else-if="filteredDetailMedia.length === 0" :icon="Search" title="该筛选条件下暂无作品">
          <UiButton variant="secondary" size="sm" @click="detailTypeFilter = 'all'">查看全部</UiButton>
        </EmptyState>

        <div v-else class="creator-media-grid poster-grid">
          <MediaCard
            v-for="item in filteredDetailMedia"
            :key="item.id"
            :media="item"
            @click="openMedia(item)"
          />
        </div>
      </div>
    </div>

    <MediaDetail
      v-if="selectedMedia"
      :initial-media="selectedMedia"
      :all-media="filteredDetailMedia"
      @close="closeMedia"
      @updated="updateMediaInList"
      @navigate="openMedia($event, true)"
    />
  </div>
  </div>
</template>
