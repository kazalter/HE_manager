<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Loader2, Search } from 'lucide-vue-next'
import type { PawchiveCapabilities, PawchiveCreatorCandidate, PawchivePost, PawchiveScope } from '../../../types/pawchive'
import PawchiveCreatorCard from './PawchiveCreatorCard.vue'
import PawchivePostCard from './PawchivePostCard.vue'

const props = defineProps<{
  scope: PawchiveScope
  posts: PawchivePost[]
  status: 'idle' | 'loading' | 'ready' | 'error'
  loadingMore: boolean
  hasMore: boolean
  error: string
  warnings: string[]
  capabilities: PawchiveCapabilities | null
  selectedKeys: string[]
  downloadBusy: boolean
  favoriteCreatorKeys?: string[]
  favoriteBusyKeys?: string[]
  accountConnected?: boolean
}>()
const emit = defineEmits<{
  scope: [scope: PawchiveScope]
  more: []
  open: [index: number]
  select: [post: PawchivePost]
  favorite: [creator: Pick<PawchiveCreatorCandidate, 'service' | 'creator_id' | 'creator_name' | 'source_url'>]
  downloadSelected: []
}>()
const creatorKey = (creator: Pick<PawchiveCreatorCandidate, 'service' | 'creator_id'>) => `${creator.service}/${creator.creator_id}`
const draft = ref(props.scope.query)
const draftTag = ref(props.scope.tag)
watch(() => props.scope.query, value => { draft.value = value })
watch(() => props.scope.tag, value => { draftTag.value = value })
const scopeLabel = computed(() => props.scope.creatorId
  ? `创作者 ${props.scope.service} · ${props.scope.creatorId}`
  : props.scope.query ? `搜索作者：${props.scope.query}` : '最新作者')
const creatorResults = computed<PawchiveCreatorCandidate[]>(() => {
  const creators = new Map<string, PawchiveCreatorCandidate>()
  for (const post of props.posts) {
    const key = creatorKey(post)
    const existing = creators.get(key)
    if (existing) {
      existing.post_count += 1
      continue
    }
    creators.set(key, {
      service: post.service,
      creator_id: post.creator_id,
      creator_name: post.creator_name,
      source_url: post.source_url,
      post_count: 1,
      latest_post: post,
    })
  }
  return [...creators.values()]
})

const search = () => {
  const query = draft.value.trim()
  const directCreator = query.match(/^(?:https?:\/\/(?:www\.)?pawchive\.pw\/)?([A-Za-z0-9_-]+)\/user\/([A-Za-z0-9_-]+)\/?$/i)
    || query.match(/^([A-Za-z0-9_-]+)\/([A-Za-z0-9_-]+)$/)
  if (directCreator) {
    emit('scope', { ...props.scope, query: '', service: directCreator[1], creatorId: directCreator[2], tag: '' })
    return
  }
  if (query && query.length < 3) return
  emit('scope', { ...props.scope, query, tag: props.scope.creatorId ? draftTag.value.trim() : '' })
}
const applyFilters = () => emit('scope', { ...props.scope, tag: props.scope.creatorId ? draftTag.value.trim() : '' })
const showCreator = (post: PawchivePost) => emit('scope', {
  query: '', service: post.service, creatorId: post.creator_id, tag: '', mediaType: props.scope.mediaType,
})
const openCreator = (creator: PawchiveCreatorCandidate) => emit('scope', {
  query: '', service: creator.service, creatorId: creator.creator_id, tag: '', mediaType: props.scope.mediaType,
})
const showLatest = () => emit('scope', { query: '', service: '', creatorId: '', tag: '', mediaType: 'all' })
</script>

<template>
  <section class="space-y-5">
    <form class="flex flex-col sm:flex-row gap-3" @submit.prevent="search">
      <label class="flex-1 min-w-0">
        <span class="block text-xs font-semibold text-white/65 mb-2">{{ scope.creatorId ? '搜索该作者的帖子' : '搜索作者或帖子' }}</span>
        <span class="flex items-center gap-2 bg-black/20 border border-white/15 rounded-xl px-3 focus-within:ring-2 focus-within:ring-accent/60">
          <Search :size="18" class="text-white/45 shrink-0" aria-hidden="true" />
        <input v-model="draft" type="search" class="w-full min-h-11 bg-transparent outline-none text-sm text-white placeholder-white/35" :placeholder="scope.creatorId ? '至少输入 3 个字符' : '关键词、作者页链接或服务/ID'" />
        </span>
      </label>
      <button type="submit" :disabled="!!draft.trim() && draft.trim().length < 3 && !/^(?:https?:\/\/(?:www\.)?pawchive\.pw\/)?[A-Za-z0-9_-]+\/user\/[A-Za-z0-9_-]+\/?$/i.test(draft.trim()) && !/^[A-Za-z0-9_-]+\/[A-Za-z0-9_-]+$/.test(draft.trim())" class="self-end min-h-11 px-5 rounded-xl bg-accent text-white text-sm font-bold disabled:opacity-50 cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-white">搜索</button>
    </form>

    <div class="flex flex-wrap items-end gap-3 rounded-2xl border border-white/10 bg-white/[0.03] p-3">
      <label class="min-w-40 flex-1 sm:flex-none">
        <span class="block text-xs font-semibold text-white/65 mb-2">媒体类型</span>
        <select :value="scope.mediaType" :disabled="!capabilities" class="w-full min-h-11 rounded-xl bg-background border border-white/15 px-3 text-sm text-white disabled:opacity-50" @change="emit('scope', { ...scope, mediaType: ($event.target as HTMLSelectElement).value as PawchiveScope['mediaType'] })">
          <option value="all">全部</option><option value="image">图片</option><option value="video">视频</option>
        </select>
      </label>
      <label class="min-w-40 flex-1 sm:flex-none">
        <span class="block text-xs font-semibold text-white/65 mb-2">创作者标签</span>
        <input v-model="draftTag" type="text" :disabled="!scope.creatorId || !capabilities?.creator_tags" class="w-full min-h-11 rounded-xl bg-black/20 border border-white/15 px-3 text-sm text-white disabled:opacity-45" :placeholder="scope.creatorId ? '输入标签' : '先进入创作者范围'" />
      </label>
      <button v-if="scope.creatorId" type="button" class="min-h-11 px-4 rounded-xl border border-white/15 text-sm text-white cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="applyFilters">应用标签</button>
      <p class="text-xs text-white/50 self-center">媒体类型仅筛选打开帖子后的附件；列表仍显示当前范围的全部帖子。</p>
    </div>

    <div class="flex flex-wrap items-center justify-between gap-3">
      <div>
        <h2 class="text-lg font-bold text-white">{{ scopeLabel }}</h2>
        <p class="text-xs text-white/50">{{ scope.creatorId ? '按最新排序 · 浏览该作者的帖子' : '按最新帖子匹配并归并作者' }}</p>
      </div>
      <button v-if="scope.creatorId || scope.query" type="button" class="min-h-11 px-3 flex items-center gap-2 rounded-xl border border-white/15 text-sm text-white/75 hover:text-white cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="showLatest"><ArrowLeft :size="16" />返回作者</button>
    </div>

    <p v-for="warning in warnings" :key="warning" class="text-xs text-amber-300">{{ warning }}</p>
    <div v-if="scope.creatorId && selectedKeys.length" class="rounded-xl border border-accent/30 bg-accent/10 p-3 flex flex-wrap items-center justify-between gap-3"><p class="text-sm text-white">已选择 {{ selectedKeys.length }} 篇帖子</p><button type="button" :disabled="downloadBusy" class="min-h-11 px-4 rounded-xl bg-accent text-white text-sm font-bold disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-white" @click="emit('downloadSelected')">{{ downloadBusy ? '正在核对…' : '下载勾选帖子' }}</button></div>
    <p v-if="status === 'loading'" role="status" class="py-16 text-center text-white/65 flex items-center justify-center gap-2"><Loader2 :size="18" class="animate-spin" />正在读取帖子…</p>
    <div v-else-if="status === 'error'" role="alert" class="rounded-2xl border border-red-400/25 bg-red-400/5 p-6 text-center text-sm text-red-200"><p>{{ error }}</p><button type="button" class="mt-3 min-h-11 px-4 rounded-xl bg-white/10 cursor-pointer" @click="emit('scope', scope)">重试</button></div>
    <p v-else-if="status === 'ready' && scope.creatorId && posts.length === 0" class="py-16 text-center text-white/55">当前作者没有帖子。</p>
    <p v-else-if="status === 'ready' && !scope.creatorId && scope.query && creatorResults.length === 0" class="py-16 text-center text-white/55">没找到匹配公开帖子的作者。可以换关键词，或粘贴作者页链接 / 服务/ID 精确打开。</p>
    <p v-else-if="status === 'ready' && !scope.creatorId && posts.length === 0" class="py-16 text-center text-white/55">当前范围没有帖子。</p>
    <div v-if="!scope.creatorId && creatorResults.length" class="grid grid-cols-1 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
      <PawchiveCreatorCard
        v-for="creator in creatorResults"
        :key="creatorKey(creator)"
        :creator="creator"
        :favorite="favoriteCreatorKeys?.includes(creatorKey(creator)) || false"
        :busy="favoriteBusyKeys?.includes(creatorKey(creator)) || false"
        :can-favorite="accountConnected || false"
        @open="openCreator(creator)"
        @favorite="emit('favorite', creator)"
      />
    </div>
    <div v-if="scope.creatorId && posts.length" class="grid grid-cols-1 min-[480px]:grid-cols-2 lg:grid-cols-3 2xl:grid-cols-4 gap-4">
      <PawchivePostCard
        v-for="(post, index) in posts"
        :key="post.post_key"
        :post="post"
        :selected="selectedKeys.includes(post.post_key)"
        :favorite="favoriteCreatorKeys?.includes(creatorKey(post)) || false"
        :favorite-busy="favoriteBusyKeys?.includes(creatorKey(post)) || false"
        :can-favorite="accountConnected || false"
        @open="emit('open', index)"
        @creator="showCreator(post)"
        @select="emit('select', post)"
        @favorite="emit('favorite', post)"
      />
    </div>
    <div v-if="posts.length && (hasMore || loadingMore || error)" class="text-center">
      <p v-if="error" role="alert" class="text-sm text-red-300 mb-2">{{ error }}</p>
      <button v-if="hasMore" type="button" :disabled="loadingMore" class="min-h-11 px-6 rounded-xl border border-white/15 bg-white/5 hover:bg-white/10 text-sm font-semibold text-white disabled:opacity-50 cursor-pointer focus-visible:ring-2 focus-visible:ring-accent" @click="emit('more')">{{ loadingMore ? '正在加载…' : scope.creatorId ? '加载更多帖子' : '加载更多作者' }}</button>
    </div>
  </section>
</template>
