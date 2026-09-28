<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, ChevronLeft, ChevronRight, Clock3, Heart, Loader2, Search, Sparkles } from 'lucide-vue-next'
import type { PawchiveCapabilities, PawchiveCreator, PawchiveCreatorFavorite, PawchivePost, PawchiveScope } from '../../../types/pawchive'
import PawchiveCreatorCard from './PawchiveCreatorCard.vue'
import PawchivePostCard from './PawchivePostCard.vue'

const props = defineProps<{
  scope: PawchiveScope
  posts: PawchivePost[]
  favorites: PawchiveCreatorFavorite[]
  favoritesLoading: boolean
  accountConnected: boolean
  favoriteBusyKeys: string[]
  favoriteMessage: string
  status: 'idle' | 'loading' | 'ready' | 'error'
  loadingMore: boolean
  hasMore: boolean
  error: string
  warnings: string[]
  capabilities: PawchiveCapabilities | null
  selectedKeys: string[]
  downloadBusy: boolean
}>()
const emit = defineEmits<{
  scope: [scope: PawchiveScope]
  home: [fromCreator: boolean]
  more: []
  open: [index: number]
  openCreator: [creator: PawchiveCreator]
  favorite: [creator: PawchiveCreator]
  refresh: []
  select: [post: PawchivePost]
  downloadSelected: []
}>()

const draft = ref(props.scope.query)
const draftTag = ref(props.scope.tag)
const validationMessage = ref('')
watch(() => props.scope.query, value => { draft.value = value })
watch(() => props.scope.tag, value => { draftTag.value = value })

const favoriteKey = (creator: Pick<PawchiveCreator, 'service' | 'creator_id'>) => `${creator.service}:${creator.creator_id}`
const favoriteKeys = computed(() => new Set(props.favorites.map(favoriteKey)))
const favoriteByKey = computed(() => new Map(props.favorites.map(item => [favoriteKey(item), item])))
const PAGE_SIZE = 30
const page = ref(1)
const updatedTime = (value?: string | null) => {
  const time = value ? Date.parse(value) : NaN
  return Number.isFinite(time) ? time : 0
}
const sortedFavorites = computed(() => [...props.favorites].sort((a, b) =>
  updatedTime(b.updated_at) - updatedTime(a.updated_at) ||
  a.creator_name.localeCompare(b.creator_name, 'zh-Hans-CN')))
const creatorMatches = computed(() => {
  const grouped = new Map<string, { creator: PawchiveCreator; latestPost: PawchivePost; postCount: number }>()
  for (const post of props.posts) {
    const creator: PawchiveCreator = {
      service: post.service,
      creator_id: post.creator_id,
      creator_name: post.creator_name || post.creator_id,
      source_url: `https://pawchive.pw/${encodeURIComponent(post.service)}/user/${encodeURIComponent(post.creator_id)}`,
    }
    const key = favoriteKey(creator)
    const match = grouped.get(key)
    if (match) match.postCount++
    else grouped.set(key, { creator, latestPost: post, postCount: 1 })
  }
  return [...grouped.values()]
})
const favoriteSearchResults = computed(() => {
  const query = props.scope.query.trim().toLocaleLowerCase()
  if (!query) return []
  return sortedFavorites.value.filter(creator => [creator.creator_name, creator.service, creator.creator_id]
    .some(value => value.toLocaleLowerCase().includes(query)))
})
const favoriteSearchKeys = computed(() => new Set(favoriteSearchResults.value.map(favoriteKey)))
const matchingSearchResults = computed(() => creatorMatches.value.filter(match => !favoriteSearchKeys.value.has(favoriteKey(match.creator))))
const visibleCreators = computed(() => props.scope.query
  ? [
      ...favoriteSearchResults.value.map(creator => ({ creator, favorite: true, latestPost: null as PawchivePost | null, postCount: 0 })),
      ...matchingSearchResults.value.map(match => ({ ...match, favorite: favoriteKeys.value.has(favoriteKey(match.creator)) })),
    ]
  : sortedFavorites.value.map(creator => ({ creator, favorite: true, latestPost: null as PawchivePost | null, postCount: 0 })))
const pageCount = computed(() => Math.max(1, Math.ceil(visibleCreators.value.length / PAGE_SIZE)))
const pagedCreators = computed(() => visibleCreators.value.slice((page.value - 1) * PAGE_SIZE, page.value * PAGE_SIZE))
watch(() => [props.scope.query, props.scope.creatorId], () => { page.value = 1 })
watch(pageCount, count => { if (page.value > count) page.value = count })
const showPage = (next: number) => { page.value = Math.min(pageCount.value, Math.max(1, next)) }
const currentCreator = computed<PawchiveCreator | null>(() => {
  if (!props.scope.creatorId) return null
  const key = favoriteKey({ service: props.scope.service, creator_id: props.scope.creatorId })
  const saved = favoriteByKey.value.get(key)
  const post = props.posts.find(item => item.service === props.scope.service && item.creator_id === props.scope.creatorId)
  const creatorName = saved?.creator_name || post?.creator_name || props.scope.creatorId
  return {
    service: props.scope.service,
    creator_id: props.scope.creatorId,
    creator_name: creatorName,
    source_url: `https://pawchive.pw/${encodeURIComponent(props.scope.service)}/user/${encodeURIComponent(props.scope.creatorId)}`,
  }
})
const currentIsFavorite = computed(() => currentCreator.value ? favoriteKeys.value.has(favoriteKey(currentCreator.value)) : false)

function parseCreatorReference(value: string): { service: string; creatorId: string } | null {
  const trimmed = value.trim()
  const urlMatch = trimmed.match(/^https?:\/\/(?:www\.)?pawchive\.pw\/([A-Za-z0-9_-]+)\/user\/([A-Za-z0-9_-]+)(?:\/|$)/i)
  if (urlMatch) return { service: urlMatch[1], creatorId: urlMatch[2] }
  const idMatch = trimmed.match(/^([A-Za-z0-9_-]+)\s*\/\s*([A-Za-z0-9_-]+)$/)
  if (idMatch) return { service: idMatch[1], creatorId: idMatch[2] }
  return null
}

const search = () => {
  validationMessage.value = ''
  const query = draft.value.trim()
  const reference = parseCreatorReference(query)
  if (reference) {
    draft.value = ''
    emit('scope', { query: '', service: reference.service, creatorId: reference.creatorId, tag: '', mediaType: props.scope.mediaType })
    return
  }
  if (props.scope.creatorId && query && query.length < 3) {
    validationMessage.value = '搜索作者作品时，请输入至少 3 个字符。'
    return
  }
  emit('scope', { ...props.scope, query, tag: props.scope.creatorId ? draftTag.value.trim() : '' })
}
const applyFilters = () => emit('scope', { ...props.scope, tag: props.scope.creatorId ? draftTag.value.trim() : '' })
const openCreator = (creator: PawchiveCreator) => emit('openCreator', creator)
const toggleFavorite = (creator: PawchiveCreator) => emit('favorite', creator)
const showLatest = () => emit('home', !!props.scope.creatorId)
</script>

<template>
  <section class="space-y-7">
    <div class="relative overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-br from-accent/15 via-white/[0.04] to-white/[0.015] p-5 sm:p-6">
      <div class="pointer-events-none absolute -right-12 -top-20 h-64 w-64 rounded-full bg-accent/10 blur-3xl" aria-hidden="true"></div>
      <div class="relative flex flex-col gap-5 lg:flex-row lg:items-end lg:justify-between">
        <div class="max-w-lg">
          <div class="mb-2 inline-flex items-center gap-1.5 rounded-full border border-accent/25 bg-accent/10 px-3 py-1 text-xs font-semibold text-accent"><Sparkles :size="13" aria-hidden="true" />{{ scope.creatorId ? '创作者空间' : scope.query ? '寻找创作者' : '个人收藏' }}</div>
          <h2 class="text-xl font-bold tracking-tight text-white sm:text-2xl">{{ scope.creatorId ? currentCreator?.creator_name : scope.query ? '搜索作者' : '喜欢的作者，最新动态' }}</h2>
          <p class="mt-2 text-sm leading-6 text-white/70">{{ scope.creatorId ? '浏览这位作者的帖子与附件。' : scope.query ? '账号收藏优先，其他结果从公开帖子中寻找。' : '从 Pawchive 账号同步收藏，最近更新的作者排在前面。' }}</p>
        </div>
        <form class="w-full max-w-xl" role="search" @submit.prevent="search">
          <label for="pawchive-search" class="mb-2 block text-xs font-semibold uppercase tracking-wider text-white/65">{{ scope.creatorId ? '搜索这位作者的帖子' : '搜索作者' }}</label>
          <div class="flex flex-col gap-2 sm:flex-row">
            <div class="flex min-w-0 flex-1 items-center gap-2 rounded-xl border border-white/20 bg-black/25 px-3 focus-within:border-accent/70 focus-within:ring-2 focus-within:ring-accent/25">
              <Search :size="18" class="shrink-0 text-white/60" aria-hidden="true" />
              <input id="pawchive-search" v-model="draft" type="search" :aria-describedby="validationMessage ? 'pawchive-search-help pawchive-search-error' : 'pawchive-search-help'" class="min-h-12 w-full min-w-0 bg-transparent text-sm text-white outline-none placeholder:text-white/45" :placeholder="scope.creatorId ? '输入帖子关键词' : '作者名、关键词或作者链接'" />
            </div>
            <button type="submit" class="min-h-12 rounded-xl bg-accent px-6 text-sm font-bold text-white shadow-lg shadow-accent/20 transition-colors hover:bg-accent/85 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">搜索</button>
          </div>
          <p id="pawchive-search-help" class="mt-2 text-xs leading-5 text-white/60">{{ scope.creatorId ? '输入至少 3 个字符搜索作品；清空后搜索可返回全部作品。' : '支持作者名、帖子关键词，或粘贴作者链接 / 服务/ID。少于 3 个字符时仅搜索账号收藏。' }}</p>
        </form>
      </div>
    </div>
    <p v-if="validationMessage" id="pawchive-search-error" role="alert" class="text-xs text-amber-200">{{ validationMessage }}</p>
    <p v-if="favoriteMessage" role="alert" class="text-xs text-red-200">{{ favoriteMessage }}</p>

    <div v-if="scope.creatorId" class="flex flex-wrap items-end gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
      <label class="min-w-40 flex-1 sm:flex-none">
        <span class="block text-xs font-semibold text-white/65 mb-2">媒体类型</span>
        <select :value="scope.mediaType" :disabled="!capabilities" class="w-full min-h-11 rounded-xl bg-background border border-white/15 px-3 text-sm text-white disabled:opacity-50" @change="emit('scope', { ...scope, mediaType: ($event.target as HTMLSelectElement).value as PawchiveScope['mediaType'] })">
          <option value="all">全部</option><option value="image">图片</option><option value="video">视频</option>
        </select>
      </label>
      <label class="min-w-40 flex-1 sm:flex-none">
        <span class="block text-xs font-semibold text-white/65 mb-2">作者标签</span>
        <input v-model="draftTag" type="text" :disabled="!capabilities?.creator_tags" class="w-full min-h-11 rounded-xl bg-black/20 border border-white/15 px-3 text-sm text-white disabled:opacity-45" placeholder="输入标签" />
      </label>
      <button type="button" :disabled="!capabilities?.creator_tags" class="min-h-11 px-4 rounded-xl border border-white/15 text-sm text-white disabled:opacity-45 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="applyFilters">应用标签</button>
      <p class="text-xs text-white/50 self-center">媒体类型筛选作者帖子中的附件；标签由 Pawchive 按作者范围应用。</p>
    </div>

    <div v-if="scope.creatorId" class="flex flex-wrap items-end justify-between gap-4 border-b border-white/10 pb-4">
      <div>
        <div class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-accent"><Sparkles :size="14" aria-hidden="true" />WORKS</div>
        <h3 class="text-xl font-bold tracking-tight text-white sm:text-2xl">作者作品</h3>
        <p class="mt-1 text-sm text-white/65">{{ scope.service }} · {{ scope.creatorId }} · 已载入 {{ posts.length }} 篇 · 按最新发布排序</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <button v-if="currentCreator" type="button" :disabled="!accountConnected || favoriteBusyKeys.includes(favoriteKey(currentCreator))" class="min-h-11 rounded-xl border border-white/20 bg-white/[0.05] px-4 text-sm font-semibold text-white/85 transition-colors hover:bg-white/10 disabled:opacity-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" :aria-pressed="currentIsFavorite" @click="toggleFavorite(currentCreator)">{{ currentIsFavorite ? '已收藏作者' : '收藏作者' }}</button>
        <button type="button" class="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/20 bg-white/[0.05] px-4 text-sm font-semibold text-white/80 transition-colors hover:bg-white/10 hover:text-white cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="showLatest"><ArrowLeft :size="16" aria-hidden="true" />返回作者</button>
      </div>
    </div>

    <p v-for="warning in warnings" :key="warning" class="text-xs text-amber-300">{{ warning }}</p>

    <template v-if="!scope.creatorId">
      <section aria-labelledby="pawchive-creators-heading" class="space-y-5">
        <div class="flex flex-wrap items-end justify-between gap-4 border-b border-white/10 pb-4">
          <div>
            <div class="mb-2 flex items-center gap-2 text-xs font-semibold uppercase tracking-[0.16em] text-accent"><Heart :size="14" :fill="scope.query ? 'none' : 'currentColor'" aria-hidden="true" />{{ scope.query ? 'DISCOVER' : 'FAVORITES' }}</div>
            <h3 id="pawchive-creators-heading" class="text-xl font-bold tracking-tight text-white sm:text-2xl">{{ scope.query ? `“${scope.query}”的结果` : '我喜欢的作者' }}</h3>
            <p class="mt-1 text-sm text-white/65">{{ scope.query ? '先显示账号收藏，再显示公开帖子匹配的作者。' : accountConnected ? `共 ${favorites.length} 位 · 按最近更新时间排序` : '登录 Pawchive 后，你收藏的作者会显示在这里。' }}</p>
          </div>
          <div class="flex flex-wrap items-center gap-2">
            <button v-if="scope.query" type="button" class="min-h-11 rounded-xl border border-white/20 bg-white/[0.05] px-4 text-sm font-semibold text-white/80 transition-colors hover:bg-white/10 hover:text-white cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="showLatest">返回我的收藏</button>
            <button v-else-if="accountConnected" type="button" :disabled="favoritesLoading" class="inline-flex min-h-11 items-center gap-2 rounded-xl border border-white/20 bg-white/[0.05] px-4 text-sm font-semibold text-white/80 transition-colors hover:bg-white/10 hover:text-white disabled:opacity-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="emit('refresh')"><Clock3 :size="16" aria-hidden="true" />{{ favoritesLoading ? '同步中…' : '刷新收藏' }}</button>
          </div>
        </div>

        <div v-if="(scope.query && status === 'loading') || (!scope.query && favoritesLoading)" role="status" class="flex items-center gap-2 rounded-2xl border border-white/10 bg-white/[0.03] p-5 text-sm text-white/75"><Loader2 :size="18" class="animate-spin text-accent" aria-hidden="true" />{{ scope.query ? '正在搜索公开帖子…' : '正在同步喜欢的作者…' }}</div>
        <div v-if="scope.query && status === 'error'" role="alert" class="rounded-2xl border border-red-400/25 bg-red-400/5 p-5 text-sm text-red-200"><p>{{ error }}</p><button type="button" class="mt-3 min-h-11 rounded-xl bg-white/10 px-4 cursor-pointer" @click="emit('scope', scope)">重试搜索</button></div>
        <div v-if="pagedCreators.length && (scope.query || !favoritesLoading)" class="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-4 xl:grid-cols-5 sm:gap-4">
          <PawchiveCreatorCard v-for="entry in pagedCreators" :key="favoriteKey(entry.creator)" :creator="entry.creator" :latest-post="entry.latestPost" :post-count="entry.postCount" :favorite="entry.favorite" :busy="favoriteBusyKeys.includes(favoriteKey(entry.creator))" :can-favorite="accountConnected" @open="openCreator(entry.creator)" @favorite="toggleFavorite(entry.creator)" />
        </div>
        <div v-else-if="!scope.query && !favoritesLoading && !accountConnected" class="rounded-2xl border border-dashed border-white/20 bg-white/[0.025] p-8 text-center"><Heart :size="28" class="mx-auto mb-3 text-accent" aria-hidden="true" /><p class="font-semibold text-white">先连接你的 Pawchive 账号</p><p class="mt-1 text-sm text-white/65">登录后自动同步喜欢的作者，也可以搜索并收藏新作者。</p></div>
        <div v-else-if="!scope.query && !favoritesLoading && accountConnected && !favoriteMessage" class="rounded-2xl border border-dashed border-white/20 bg-white/[0.025] p-8 text-center"><Heart :size="28" class="mx-auto mb-3 text-accent" aria-hidden="true" /><p class="font-semibold text-white">还没有喜欢的作者</p><p class="mt-1 text-sm text-white/65">搜索作者后，点击卡片上的收藏按钮即可加入这里。</p></div>
        <p v-else-if="scope.query && status === 'ready' && !visibleCreators.length" class="rounded-2xl border border-dashed border-white/20 bg-white/[0.025] p-8 text-center text-sm text-white/70">暂时没有匹配作者。试试别的关键词，或粘贴作者页链接 / 服务/ID。</p>

        <nav v-if="pageCount > 1" aria-label="作者分页" class="flex flex-wrap items-center justify-between gap-3 border-t border-white/10 pt-4">
          <p class="text-sm text-white/65">第 {{ page }} / {{ pageCount }} 页 · 每页最多 30 位作者</p>
          <div class="flex items-center gap-2">
            <button type="button" :disabled="page === 1" class="inline-flex min-h-11 items-center gap-1 rounded-xl border border-white/20 px-4 text-sm font-semibold text-white disabled:opacity-35 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="showPage(page - 1)"><ChevronLeft :size="16" aria-hidden="true" />上一页</button>
            <button type="button" :disabled="page === pageCount" class="inline-flex min-h-11 items-center gap-1 rounded-xl border border-white/20 px-4 text-sm font-semibold text-white disabled:opacity-35 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="showPage(page + 1)">下一页<ChevronRight :size="16" aria-hidden="true" /></button>
          </div>
        </nav>
      </section>
    </template>

    <template v-else>
      <div v-if="selectedKeys.length" class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-accent/35 bg-accent/10 px-4 py-3">
        <p class="text-sm font-semibold text-white">已选择 {{ selectedKeys.length }} 篇作品</p>
        <button type="button" :disabled="downloadBusy" class="min-h-11 rounded-xl bg-accent px-5 text-sm font-bold text-white shadow-lg shadow-accent/20 disabled:opacity-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white" @click="emit('downloadSelected')">{{ downloadBusy ? '正在核对…' : '下载选中作品' }}</button>
      </div>
      <p v-if="status === 'loading'" role="status" class="flex items-center justify-center gap-2 py-16 text-center text-white/70"><Loader2 :size="18" class="animate-spin text-accent" aria-hidden="true" />正在读取作者作品…</p>
      <div v-else-if="status === 'error'" role="alert" class="rounded-2xl border border-red-400/25 bg-red-400/5 p-6 text-center text-sm text-red-200"><p>{{ error }}</p><button type="button" class="mt-3 min-h-11 px-4 rounded-xl bg-white/10 cursor-pointer" @click="emit('scope', scope)">重试</button></div>
      <p v-else-if="status === 'ready' && posts.length === 0" class="rounded-2xl border border-dashed border-white/20 bg-white/[0.025] py-16 text-center text-sm text-white/70">这位作者暂时没有符合条件的作品。</p>
      <div v-if="posts.length" class="grid grid-cols-2 gap-3 sm:grid-cols-3 sm:gap-4 lg:grid-cols-4 xl:grid-cols-5">
        <PawchivePostCard v-for="(post, index) in posts" :key="post.post_key" :post="post" :selected="selectedKeys.includes(post.post_key)" @open="emit('open', index)" @select="emit('select', post)" />
      </div>
    </template>

    <div v-if="scope.creatorId || scope.query" class="text-center">
      <p v-if="error && posts.length" role="alert" class="text-sm text-red-300 mb-2">{{ error }}</p>
      <button v-if="hasMore" type="button" :disabled="loadingMore" class="min-h-11 px-6 rounded-xl border border-white/15 bg-white/5 hover:bg-white/10 text-sm font-semibold text-white disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="emit('more')">{{ loadingMore ? '正在加载…' : scope.creatorId ? '加载更多帖子' : '加载更多搜索结果' }}</button>
    </div>
  </section>
</template>
