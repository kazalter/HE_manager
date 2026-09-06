<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import axios from 'axios'
import { ArrowLeft, ExternalLink, Palette, Search, SortAsc } from 'lucide-vue-next'
import { API_BASE_URL, thumbnailUrl } from '../config'
import type { Creator, CreatorDetail, Media } from '../types'
import MediaCard from '../components/MediaCard.vue'
import { AsyncMediaDetail as MediaDetail } from '../components/asyncComponents'

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
const xProfileUrl = (sn: string) => `https://x.com/${sn}`
</script>

<template>
  <div class="z-10 relative">
  <!-- Single root element above: <transition mode="out-in"> in App.vue cannot
       drive a multi-root component. Keep this <div> the sole root node — no
       sibling comments at <template> root, since in dev mode Vue keeps comment
       vnodes and they would re-introduce the multi-root blank-page bug. -->
  <!-- ===== list mode ===== -->
  <div v-if="!isDetail">
    <header class="sticky top-0 z-40 bg-background/75 backdrop-blur-xl border-b border-white/10 px-6 md:px-8 py-5 mb-6">
      <div class="flex flex-wrap items-center justify-between gap-5">
        <div class="flex items-baseline gap-3">
          <h1 class="text-2xl md:text-3xl font-black text-white tracking-tight flex items-center gap-3">
            <Palette :size="26" class="text-accent" /> 创作者
          </h1>
          <p class="text-[11px] font-bold text-accent bg-accent/10 px-2 py-0.5 rounded-full border border-accent/20 uppercase tracking-widest">
            {{ creators.length }} 位
          </p>
        </div>

        <div class="flex flex-1 min-w-[260px] max-w-3xl gap-3">
          <div class="relative flex-1 group">
            <Search class="absolute left-4 top-1/2 -translate-y-1/2 text-white/30 group-focus-within:text-accent transition-colors" :size="18" />
            <input
              v-model="search"
              type="text"
              placeholder="搜索作者名 / @用户名…"
              class="w-full bg-white/5 border border-white/10 rounded-xl pl-12 pr-4 py-3 text-sm text-white placeholder-white/35 focus:outline-none focus:ring-2 focus:ring-accent/50 focus:bg-white/10 transition-all"
            />
          </div>
          <div class="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl p-1">
            <button
              v-for="opt in [{ k: 'count', t: '作品数' }, { k: 'pending', t: '待入库' }, { k: 'name', t: '名称' }]"
              :key="opt.k"
              @click="sortBy = opt.k as any"
              :class="sortBy === opt.k ? 'bg-accent text-white' : 'text-white/45 hover:text-white'"
              class="px-3 py-1.5 rounded-lg text-xs font-bold transition-all flex items-center gap-1"
            >
              <SortAsc v-if="opt.k === 'name'" :size="13" />{{ opt.t }}
            </button>
          </div>
        </div>
      </div>

      <div v-if="availableLetters.length > 2" class="flex flex-wrap items-center gap-1.5 pt-3 border-t border-white/8 mt-4">
        <span class="text-xs font-bold text-white/35 mr-1">首字母:</span>
        <button
          v-for="l in availableLetters"
          :key="l"
          type="button"
          @click="selectedLetter = l"
          :class="selectedLetter === l ? 'bg-accent text-white font-black' : 'text-white/50 hover:text-white hover:bg-white/10'"
          class="min-w-7 h-7 px-2 rounded-lg text-xs transition-all flex items-center justify-center cursor-pointer"
        >
          {{ l === 'ALL' ? '全部' : l }}
        </button>
      </div>
    </header>

    <div class="px-6 md:px-8 pb-12">
      <div v-if="listLoading" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-5 md:gap-7">
        <div v-for="i in 12" :key="i" class="aspect-[3/4] bg-white/5 animate-pulse rounded-2xl border border-white/5"></div>
      </div>

      <div
        v-else-if="displayedCreators.length > 0"
        class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-5 md:gap-7"
      >
        <button
          v-for="c in displayedCreators"
          :key="c.key"
          @click="c.screen_name && openCreator(c.screen_name)"
          :disabled="!c.screen_name"
          class="group text-left flex flex-col cursor-pointer transition-all duration-300 hover:-translate-y-1 focus:outline-none focus:ring-2 focus:ring-accent/50 rounded-2xl"
        >
          <div class="aspect-[3/4] relative overflow-hidden bg-sidebar/70 rounded-2xl border border-white/10 shadow-lg group-hover:shadow-2xl group-hover:shadow-accent/10 group-hover:border-white/20 transition-all duration-300">
            <img
              v-if="c.cover_path"
              :src="thumbnailUrl(c.cover_path)"
              :alt="displayName(c)"
              class="w-full h-full object-cover transition-transform duration-500 group-hover:scale-105"
              loading="eager"
              decoding="async"
            />
            <div v-else class="w-full h-full flex items-center justify-center text-white/15">
              <Palette :size="40" />
            </div>
            <div class="absolute inset-x-0 bottom-0 h-2/3 bg-gradient-to-t from-black/80 to-transparent"></div>
            <div
              v-if="c.posts_pending > 0"
              class="absolute top-2 right-2 px-2 py-1 rounded-lg bg-accent/85 backdrop-blur-md text-[10px] font-black text-white"
              :title="`还有 ${c.posts_pending} 条已知推文未入库`"
            >
              +{{ c.posts_pending }} 待入库
            </div>
            <div class="absolute inset-x-0 bottom-0 p-3">
              <h3 class="text-sm font-black text-white line-clamp-1" :title="displayName(c)">{{ displayName(c) }}</h3>
              <p class="text-[11px] text-white/55 truncate">@{{ c.screen_name }}</p>
            </div>
          </div>
          <div class="mt-2.5 px-1 flex items-center justify-between text-[11px] text-white/45 font-medium">
            <span>{{ c.media_count }} 件作品</span>
            <span>{{ c.posts_known }} 推</span>
          </div>
        </button>
      </div>

      <div v-else-if="creators.length > 0" class="flex flex-col items-center justify-center py-24 text-white/40 text-center">
        <p class="text-base font-bold">首字母「{{ selectedLetter }}」下暂无创作者</p>
        <button type="button" @click="selectedLetter = 'ALL'" class="mt-2 text-sm text-accent underline cursor-pointer">
          查看全部创作者
        </button>
      </div>

      <div v-else class="flex flex-col items-center justify-center py-32 text-white/35 text-center">
        <div class="w-16 h-16 rounded-2xl bg-white/5 flex items-center justify-center mb-5 border border-white/10">
          <Palette :size="28" />
        </div>
        <p class="text-lg font-bold mb-2">还没有可聚合的创作者</p>
        <p class="text-sm">导入一些 X（推特）喜欢后，作者会自动出现在这里。</p>
      </div>
    </div>
  </div>

  <!-- ===== detail mode ===== -->
  <div v-else>
    <header class="sticky top-0 z-40 bg-background/75 backdrop-blur-xl border-b border-white/10 px-6 md:px-8 py-5 mb-6">
      <div class="flex flex-wrap items-center justify-between gap-4">
        <div class="flex items-center gap-4 min-w-0">
          <button
            @click="handleBack"
            class="p-2.5 rounded-xl bg-white/5 border border-white/10 text-white/60 hover:text-white hover:bg-white/10 transition-all cursor-pointer"
            title="返回创作者列表"
          >
            <ArrowLeft :size="18" />
          </button>
          <div class="min-w-0">
            <h1 class="text-xl md:text-2xl font-black text-white tracking-tight truncate">
              {{ detail?.creator.display_name || '@' + screenName }}
            </h1>
            <div class="flex items-center gap-3 text-xs text-white/45 mt-0.5">
              <a
                :href="xProfileUrl(screenName)"
                target="_blank"
                rel="noopener"
                class="flex items-center gap-1 hover:text-accent transition-colors"
              >@{{ screenName }} <ExternalLink :size="12" /></a>
              <span v-if="detail">· {{ detail.creator.media_count }} 件作品</span>
              <span v-if="detail && detail.creator.posts_pending > 0" class="text-accent">
                · {{ detail.creator.posts_pending }} 条推文待入库
              </span>
            </div>
          </div>
        </div>

        <div class="flex flex-wrap items-center gap-3">
          <!-- Type filter tabs -->
          <div class="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl p-1 text-xs">
            <button
              v-for="t in [
                { k: 'all', label: '全部', count: detailMedia.length },
                { k: 'image', label: '杂图', count: mediaTypesInDetail['image'] || 0 },
                { k: 'manga', label: '漫画', count: mediaTypesInDetail['manga'] || 0 },
                { k: 'video', label: '视频', count: mediaTypesInDetail['video'] || 0 },
                { k: 'audio', label: '音频', count: mediaTypesInDetail['audio'] || 0 },
              ].filter(x => x.k === 'all' || x.count > 0)"
              :key="t.k"
              @click="detailTypeFilter = t.k"
              :class="detailTypeFilter === t.k ? 'bg-accent text-white font-bold' : 'text-white/45 hover:text-white'"
              class="px-2.5 py-1 rounded-lg transition-all cursor-pointer"
            >
              {{ t.label }} ({{ t.count }})
            </button>
          </div>

          <!-- Sort selector -->
          <div class="flex items-center gap-1 bg-white/5 border border-white/10 rounded-xl p-1 text-xs">
            <button
              v-for="s in [
                { k: 'desc', label: '最新' },
                { k: 'asc', label: '最早' },
                { k: 'rating', label: '评分' },
                { k: 'title', label: '标题' },
              ]"
              :key="s.k"
              @click="detailSort = s.k as any"
              :class="detailSort === s.k ? 'bg-accent text-white font-bold' : 'text-white/45 hover:text-white'"
              class="px-2.5 py-1 rounded-lg transition-all cursor-pointer"
            >
              {{ s.label }}
            </button>
          </div>
        </div>
      </div>
    </header>

    <div class="px-6 md:px-8 pb-12">
      <div v-if="detailLoading" class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-5 md:gap-7">
        <div v-for="i in 12" :key="i" class="aspect-[3/4.5] bg-white/5 animate-pulse rounded-2xl border border-white/5"></div>
      </div>

      <div v-else-if="detailError" class="py-24 text-center text-white/40">{{ detailError }}</div>

      <div v-else-if="filteredDetailMedia.length === 0" class="py-24 text-center text-white/40">
        该筛选条件下暂无作品。
      </div>

      <div
        v-else
        class="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 2xl:grid-cols-6 gap-5 md:gap-7"
      >
        <MediaCard
          v-for="item in filteredDetailMedia"
          :key="item.id"
          :media="item"
          @click="openMedia(item)"
        />
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
