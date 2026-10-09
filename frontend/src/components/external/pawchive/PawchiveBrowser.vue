<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, ChevronLeft, ChevronRight, Heart, ImageOff, RefreshCw, Search, SearchX, TriangleAlert, Users } from 'lucide-vue-next'
import { EmptyState, UiButton, UiInput, UiSpinner, controlClass, fieldHintClass, fieldLabelClass } from '../../ui'
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
  <section class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div class="min-w-0">
        <div class="flex min-w-0 items-baseline gap-2.5">
          <h2 :id="scope.creatorId ? undefined : 'pawchive-creators-heading'" class="truncate text-heading font-semibold text-ink">
            {{ scope.creatorId ? currentCreator?.creator_name : scope.query ? `“${scope.query}”的结果` : '我喜欢的作者' }}
          </h2>
          <span v-if="!scope.creatorId && !scope.query && accountConnected" class="shrink-0 text-meta text-subtle tabular-nums">{{ favorites.length }} 位</span>
        </div>
        <p class="mt-0.5 text-meta text-subtle">
          <template v-if="scope.creatorId"><span class="tabular-nums">{{ scope.service }} · {{ scope.creatorId }} · 已载入 {{ posts.length }} 篇</span> · 按最新发布排序</template>
          <template v-else-if="scope.query">先显示账号收藏，再显示公开帖子匹配的作者。</template>
          <template v-else>{{ accountConnected ? '最近更新的作者排在前面。' : '登录 Pawchive 后，你收藏的作者会显示在这里。' }}</template>
        </p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <template v-if="scope.creatorId">
          <UiButton variant="ghost" size="sm" @click="showLatest">
            <template #icon><ArrowLeft :size="14" aria-hidden="true" /></template>
            返回作者
          </UiButton>
          <button
            v-if="currentCreator"
            type="button"
            :disabled="!accountConnected || favoriteBusyKeys.includes(favoriteKey(currentCreator))"
            :aria-pressed="currentIsFavorite"
            class="inline-flex h-8 shrink-0 items-center gap-1.5 whitespace-nowrap rounded-lg border px-3 text-meta font-medium transition-colors focus-ring disabled:opacity-45"
            :class="currentIsFavorite ? 'border-accent/50 bg-accent/15 text-accent-glow' : 'border-line bg-surface-2 text-ink hover:border-line-strong hover:bg-surface-3'"
            @click="toggleFavorite(currentCreator)"
          >
            <Heart :size="14" :fill="currentIsFavorite ? 'currentColor' : 'none'" aria-hidden="true" />
            {{ currentIsFavorite ? '已收藏作者' : '收藏作者' }}
          </button>
        </template>
        <UiButton v-else-if="scope.query" size="sm" @click="showLatest">返回我的收藏</UiButton>
        <UiButton v-else-if="accountConnected" size="sm" variant="ghost" :loading="favoritesLoading" @click="emit('refresh')">
          <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
          {{ favoritesLoading ? '同步中…' : '刷新收藏' }}
        </UiButton>
      </div>
    </div>

    <form role="search" @submit.prevent="search">
      <label for="pawchive-search" class="sr-only">{{ scope.creatorId ? '搜索这位作者的帖子' : '搜索作者' }}</label>
      <div class="flex gap-2">
        <UiInput
          id="pawchive-search"
          v-model="draft"
          type="search"
          class="flex-1"
          :aria-describedby="validationMessage ? 'pawchive-search-help pawchive-search-error' : 'pawchive-search-help'"
          :placeholder="scope.creatorId ? '搜索这位作者的帖子' : '作者名、关键词或作者链接'"
        >
          <template #leading><Search :size="16" /></template>
        </UiInput>
        <UiButton type="submit" variant="primary">搜索</UiButton>
      </div>
      <p id="pawchive-search-help" :class="fieldHintClass">{{ scope.creatorId ? '输入至少 3 个字符搜索作品；清空后搜索可返回全部作品。' : '支持作者名、帖子关键词，或粘贴作者链接 / 服务/ID。少于 3 个字符时仅搜索账号收藏。' }}</p>
    </form>
    <p v-if="validationMessage" id="pawchive-search-error" role="alert" class="-mt-3 text-caption text-warning">{{ validationMessage }}</p>
    <p v-if="favoriteMessage" role="alert" class="rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta text-danger">{{ favoriteMessage }}</p>

    <div v-if="scope.creatorId" class="space-y-2 border-y border-line py-4">
      <div class="grid grid-cols-[104px_minmax(0,1fr)_auto] items-end gap-2 sm:flex sm:gap-3">
        <label class="block sm:w-32">
          <span :class="fieldLabelClass">媒体类型</span>
          <select :value="scope.mediaType" :disabled="!capabilities" :class="[controlClass('md'), 'select-native']" @change="emit('scope', { ...scope, mediaType: ($event.target as HTMLSelectElement).value as PawchiveScope['mediaType'] })">
            <option value="all">全部</option><option value="image">图片</option><option value="video">视频</option>
          </select>
        </label>
        <label class="block min-w-0 sm:w-60">
          <span :class="fieldLabelClass">作者标签</span>
          <UiInput v-model="draftTag" :disabled="!capabilities?.creator_tags" placeholder="输入标签" />
        </label>
        <UiButton :disabled="!capabilities?.creator_tags" @click="applyFilters">应用标签</UiButton>
      </div>
      <p class="text-caption text-subtle">媒体类型筛选作者帖子中的附件；标签由 Pawchive 按作者范围应用。</p>
    </div>

    <p v-for="warning in warnings" :key="warning" class="flex items-start gap-2 rounded-lg border border-warning/25 bg-warning/10 px-3.5 py-3 text-meta text-warning">{{ warning }}</p>

    <template v-if="!scope.creatorId">
      <section aria-labelledby="pawchive-creators-heading" class="space-y-5">
        <p v-if="(scope.query && status === 'loading') || (!scope.query && favoritesLoading)" role="status" class="flex items-center justify-center gap-2 py-12 text-meta text-subtle"><UiSpinner :size="16" />{{ scope.query ? '正在搜索公开帖子…' : '正在同步喜欢的作者…' }}</p>
        <div v-if="scope.query && status === 'error'" role="alert" class="rounded-2xl border border-line bg-surface">
          <EmptyState compact tone="danger" :icon="TriangleAlert" title="搜索失败" :description="error">
            <UiButton size="sm" @click="emit('scope', scope)">重试搜索</UiButton>
          </EmptyState>
        </div>
        <div v-if="pagedCreators.length && (scope.query || !favoritesLoading)" class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-4">
          <PawchiveCreatorCard v-for="entry in pagedCreators" :key="favoriteKey(entry.creator)" :creator="entry.creator" :latest-post="entry.latestPost" :post-count="entry.postCount" :favorite="entry.favorite" :busy="favoriteBusyKeys.includes(favoriteKey(entry.creator))" :can-favorite="accountConnected" @open="openCreator(entry.creator)" @favorite="toggleFavorite(entry.creator)" />
        </div>
        <div v-else-if="!scope.query && !favoritesLoading && !accountConnected" class="rounded-2xl border border-dashed border-line">
          <EmptyState :icon="Users" title="先连接你的 Pawchive 账号" description="登录后自动同步喜欢的作者，也可以搜索并收藏新作者。" />
        </div>
        <div v-else-if="!scope.query && !favoritesLoading && accountConnected && !favoriteMessage" class="rounded-2xl border border-dashed border-line">
          <EmptyState :icon="Heart" title="还没有喜欢的作者" description="搜索作者后，点击卡片上的收藏按钮即可加入这里。" />
        </div>
        <div v-else-if="scope.query && status === 'ready' && !visibleCreators.length" class="rounded-2xl border border-dashed border-line">
          <EmptyState :icon="SearchX" title="暂时没有匹配作者" description="试试别的关键词，或粘贴作者页链接 / 服务/ID。" />
        </div>

        <nav v-if="pageCount > 1" aria-label="作者分页" class="flex flex-wrap items-center justify-between gap-3 border-t border-line pt-4">
          <p class="text-meta text-subtle tabular-nums">第 {{ page }} / {{ pageCount }} 页 · 每页最多 30 位作者</p>
          <div class="flex items-center gap-2">
            <UiButton size="sm" :disabled="page === 1" @click="showPage(page - 1)">
              <template #icon><ChevronLeft :size="14" aria-hidden="true" /></template>
              上一页
            </UiButton>
            <UiButton size="sm" :disabled="page === pageCount" @click="showPage(page + 1)">
              下一页
              <template #trailing><ChevronRight :size="14" aria-hidden="true" /></template>
            </UiButton>
          </div>
        </nav>
      </section>
    </template>

    <template v-else>
      <div v-if="selectedKeys.length" class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-accent/40 bg-accent/10 py-2 pl-4 pr-2">
        <p class="text-body font-medium text-ink">已选择 <span class="tabular-nums">{{ selectedKeys.length }}</span> 篇作品</p>
        <UiButton variant="primary" :loading="downloadBusy" @click="emit('downloadSelected')">{{ downloadBusy ? '正在核对…' : '下载选中作品' }}</UiButton>
      </div>
      <p v-if="status === 'loading'" role="status" class="flex items-center justify-center gap-2 py-16 text-meta text-subtle"><UiSpinner :size="16" />正在读取作者作品…</p>
      <div v-else-if="status === 'error'" role="alert" class="rounded-2xl border border-line bg-surface">
        <EmptyState compact tone="danger" :icon="TriangleAlert" title="读取失败" :description="error">
          <UiButton size="sm" @click="emit('scope', scope)">重试</UiButton>
        </EmptyState>
      </div>
      <div v-else-if="status === 'ready' && posts.length === 0" class="rounded-2xl border border-dashed border-line">
        <EmptyState :icon="ImageOff" title="没有符合条件的作品" description="这位作者暂时没有符合条件的作品，试试调整媒体类型或标签。" />
      </div>
      <div v-if="posts.length" class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-4">
        <PawchivePostCard v-for="(post, index) in posts" :key="post.post_key" :post="post" :selected="selectedKeys.includes(post.post_key)" @open="emit('open', index)" @select="emit('select', post)" />
      </div>
    </template>

    <div v-if="scope.creatorId || scope.query" class="flex flex-col items-center gap-2">
      <p v-if="error && posts.length" role="alert" class="text-meta text-danger">{{ error }}</p>
      <UiButton v-if="hasMore" :loading="loadingMore" @click="emit('more')">{{ loadingMore ? '正在加载…' : scope.creatorId ? '加载更多帖子' : '加载更多搜索结果' }}</UiButton>
    </div>
  </section>
</template>
