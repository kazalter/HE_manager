<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue'
import { Heart, RefreshCw, Search, SearchX, TriangleAlert, Users } from 'lucide-vue-next'
import { EmptyState, UiButton, UiInput, UiSpinner, controlClass } from '../../ui'
import PaginationControl from '../../PaginationControl.vue'
import PawchiveCreatorCard from './PawchiveCreatorCard.vue'
import { usePawchiveCreators } from '../../../composables/usePawchiveCreators'
import { parsePawchiveCreator, pawchiveCreatorKey } from '../../../utils/pawchiveCreator'
import type { PawchiveCreator, PawchiveCreatorFavorite, PawchiveCreatorSort } from '../../../types/pawchive'

const props = defineProps<{
  favorites: PawchiveCreatorFavorite[]
  favoritesLoading: boolean
  accountConnected: boolean
  favoriteBusyKeys: string[]
}>()
const emit = defineEmits<{
  openCreator: [creator: PawchiveCreator]
  favorite: [creator: PawchiveCreator]
  refresh: []
  login: []
}>()
const root = ref<HTMLElement | null>(null)
const view = ref<'favorites' | 'discover'>('favorites')
const draft = ref('')
const favoritePage = ref(1)
const favoriteService = ref('')
const directory = usePawchiveCreators()
const PAGE_SIZE = 30
const favoriteKeys = computed(() => new Set(props.favorites.map(pawchiveCreatorKey)))
const favorites = computed(() => [...props.favorites]
  .filter(x => !favoriteService.value || x.service === favoriteService.value)
  .sort((a, b) => (Date.parse(b.updated_at || '') || 0) - (Date.parse(a.updated_at || '') || 0)
    || a.creator_name.localeCompare(b.creator_name, 'zh-Hans-CN')))
const favoritePageCount = computed(() => Math.max(1, Math.ceil(favorites.value.length / PAGE_SIZE)))
watch(favoritePageCount, count => { favoritePage.value = Math.min(favoritePage.value, count) })
const visible = computed(() => view.value === 'favorites'
  ? favorites.value.slice((favoritePage.value - 1) * PAGE_SIZE, favoritePage.value * PAGE_SIZE)
  : directory.items.value)
const services = computed(() => [...new Set(['patreon', 'fanbox', 'discord', ...(directory.result.value?.services || []), ...props.favorites.map(x => x.service)])])
const label = (service: string) => ({ patreon: 'Patreon', fanbox: 'Fanbox', discord: 'Discord', fantia: 'Fantia', gumroad: 'Gumroad' }[service] || service)
const isLoading = computed(() => view.value === 'favorites' ? props.favoritesLoading : directory.status.value === 'loading')
const heading = computed(() => view.value === 'favorites' ? '我喜欢的作者' : directory.query.value
  ? `“${directory.query.value}”的作者结果` : directory.sort.value === 'updated' ? '最近更新的作者' : '热门作者')
const backLabel = computed(() => view.value === 'favorites' ? '返回我的收藏' : directory.query.value ? '返回搜索结果' : '返回发现作者')
defineExpose({ backLabel })

const switchView = (next: 'favorites' | 'discover') => {
  view.value = next
  if (next === 'discover' && directory.status.value === 'idle') void directory.load()
}
const search = () => {
  const query = draft.value.trim()
  const reference = parsePawchiveCreator(query)
  if (reference) {
    emit('openCreator', { service: reference.service, creator_id: reference.creatorId,
      creator_name: reference.creatorId, source_url: `https://pawchive.pw/${reference.service}/user/${reference.creatorId}` })
    return
  }
  view.value = 'discover'
  void directory.search({ query, sort: query ? 'relevance' : 'popular' })
}
const changeService = (event: Event) => {
  const service = (event.target as HTMLSelectElement).value
  favoritePage.value = 1
  if (view.value === 'discover') void directory.search({ service })
  else favoriteService.value = service
}
const changeSort = (event: Event) => void directory.search({ sort: (event.target as HTMLSelectElement).value as PawchiveCreatorSort })
const changePage = async (page: number) => {
  if (view.value === 'favorites') favoritePage.value = page
  else await directory.search({ page })
  await nextTick()
  root.value?.scrollIntoView?.({ block: 'start', behavior: 'auto' })
}
onBeforeUnmount(directory.dispose)
</script>

<template>
  <section ref="root" class="min-w-0 scroll-mt-28 space-y-5">
    <nav aria-label="Pawchive 作者范围" class="flex gap-6 border-b border-line">
      <button v-for="option in ([{ value: 'favorites', text: '我的收藏' }, { value: 'discover', text: '发现作者' }] as const)"
        :key="option.value" type="button" :aria-current="view === option.value ? 'page' : undefined"
        class="inline-flex min-h-11 items-center gap-2 border-b-2 pb-2 pt-1 text-body transition-colors focus-ring-inset"
        :class="view === option.value ? 'border-accent font-medium text-ink' : 'border-transparent text-subtle hover:text-ink'"
        @click="switchView(option.value)">
        {{ option.text }}<span v-if="option.value === 'favorites' && accountConnected" class="text-meta tabular-nums text-subtle">{{ props.favorites.length }}</span>
      </button>
    </nav>

    <form role="search" aria-label="全站作者搜索" @submit.prevent="search">
      <div class="flex gap-2">
        <UiInput v-model="draft" type="search" maxlength="200" class="min-w-0 flex-1" aria-label="搜索全站作者" placeholder="作者名称、ID，或粘贴作者链接">
          <template #leading><Search :size="16" /></template>
        </UiInput>
        <UiButton type="submit" variant="primary">搜索</UiButton>
      </div>
      <p class="mt-2 text-caption text-subtle">搜索全部公开作者；不必先收藏，也能进入作者作品页。</p>
    </form>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <div class="flex flex-wrap items-baseline gap-x-2.5 gap-y-1">
        <h3 class="text-heading font-semibold text-ink">{{ heading }}</h3>
        <span v-if="!isLoading && (view === 'favorites' || directory.result.value)" class="text-meta text-subtle tabular-nums">{{ view === 'favorites' ? favorites.length : directory.result.value?.total }} 位</span>
      </div>
      <div class="flex max-w-full flex-wrap items-center gap-2">
        <select :value="view === 'favorites' ? favoriteService : directory.service.value" aria-label="作者平台" :class="[controlClass('sm'), 'select-native !w-auto min-w-32 max-w-40']" @change="changeService">
          <option value="">全部平台</option><option v-for="service in services" :key="service" :value="service">{{ label(service) }}</option>
        </select>
        <select v-if="view === 'discover'" :value="directory.sort.value" aria-label="作者排序" :class="[controlClass('sm'), 'select-native !w-auto min-w-32 max-w-44']" @change="changeSort">
          <option value="popular">站内收藏最多</option><option value="updated">最近更新</option><option v-if="directory.query.value" value="relevance">相关度</option>
        </select>
        <UiButton v-if="view === 'favorites' && accountConnected" size="sm" variant="ghost" :loading="favoritesLoading" @click="emit('refresh')">
          <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>刷新收藏
        </UiButton>
      </div>
    </div>

    <p v-if="view === 'discover' && directory.result.value?.stale" role="status" class="text-meta text-warning">来源更新暂有延迟，当前显示上次成功同步的作者目录。</p>
    <p v-if="view === 'discover' && directory.result.value && !directory.result.value.popularity_available && visible.length" role="status" class="text-meta text-subtle">来源暂未提供收藏人数，当前按最近更新排序。</p>
    <p v-if="isLoading" role="status" class="flex items-center justify-center gap-2 py-12 text-meta text-subtle"><UiSpinner :size="16" />{{ view === 'favorites' ? '正在同步喜欢的作者…' : '正在读取作者目录，首次同步可能需要一些时间…' }}</p>

    <div v-else-if="view === 'discover' && directory.status.value === 'error'" role="alert" class="rounded-2xl border border-line bg-surface">
      <EmptyState compact tone="danger" :icon="TriangleAlert" title="作者目录暂时不可用" :description="directory.error.value">
        <UiButton size="sm" @click="directory.load">重新读取</UiButton>
      </EmptyState>
    </div>
    <div v-else-if="view === 'favorites' && !accountConnected" class="rounded-2xl border border-dashed border-line">
      <EmptyState :icon="Users" title="连接账号，继续你的收藏" description="发现和浏览作者无需连接 Pawchive；收藏作者时再登录即可。">
        <UiButton variant="primary" @click="switchView('discover')">发现作者</UiButton><UiButton @click="emit('login')">连接账号</UiButton>
      </EmptyState>
    </div>
    <div v-else-if="visible.length" class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-4">
      <PawchiveCreatorCard v-for="creator in visible" :key="pawchiveCreatorKey(creator)" :creator="creator"
        :favorite="favoriteKeys.has(pawchiveCreatorKey(creator))" :busy="favoriteBusyKeys.includes(pawchiveCreatorKey(creator))"
        :can-favorite="accountConnected" @open="emit('openCreator', creator)" @favorite="emit('favorite', creator)" />
    </div>
    <div v-else-if="view === 'favorites'" class="rounded-2xl border border-dashed border-line">
      <EmptyState :icon="Heart" title="还没有匹配的收藏作者" description="去发现作者，找到喜欢的创作者。"><UiButton @click="switchView('discover')">发现作者</UiButton></EmptyState>
    </div>
    <div v-else class="rounded-2xl border border-dashed border-line">
      <EmptyState :icon="SearchX" title="暂时没有匹配作者" description="试试其他名称、作者 ID，或直接粘贴作者页链接。" />
    </div>

    <PaginationControl v-if="!isLoading && ((view === 'favorites' && accountConnected && favoritePageCount > 1) || (view === 'discover' && directory.result.value && directory.result.value.total > PAGE_SIZE))"
      :page="view === 'favorites' ? favoritePage : directory.page.value"
      :page-count="view === 'favorites' ? favoritePageCount : Math.max(1, Math.ceil((directory.result.value?.total || 0) / PAGE_SIZE))"
      :total-items="view === 'favorites' ? favorites.length : directory.result.value?.total || 0" :page-size="PAGE_SIZE" item-label="位作者" @change="changePage" />
  </section>
</template>
