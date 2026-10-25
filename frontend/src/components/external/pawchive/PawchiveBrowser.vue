<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ArrowLeft, Heart, ImageOff, Search, TriangleAlert, Users } from 'lucide-vue-next'
import { EmptyState, UiButton, UiInput, UiSpinner, controlClass, fieldHintClass, fieldLabelClass } from '../../ui'
import type { PawchiveCapabilities, PawchiveCreator, PawchiveCreatorFavorite, PawchivePost, PawchiveScope } from '../../../types/pawchive'
import { pawchiveCreatorKey } from '../../../utils/pawchiveCreator'
import PawchivePostCard from './PawchivePostCard.vue'

const props = defineProps<{
  scope: PawchiveScope
  posts: PawchivePost[]
  creator?: PawchiveCreator | null
  backLabel?: string
  favorites: PawchiveCreatorFavorite[]
  accountConnected: boolean
  favoriteBusyKeys: string[]
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
  home: []
  more: []
  open: [index: number]
  favorite: [creator: PawchiveCreator]
  select: [post: PawchivePost]
  downloadSelected: []
}>()
const draft = ref(props.scope.query)
const draftTag = ref(props.scope.tag)
const validationMessage = ref('')
watch(() => props.scope.query, value => { draft.value = value })
watch(() => props.scope.tag, value => { draftTag.value = value })
const currentCreator = computed<PawchiveCreator>(() => {
  const saved = props.favorites.find(x => x.service === props.scope.service && x.creator_id === props.scope.creatorId)
  return props.creator || saved || {
    service: props.scope.service, creator_id: props.scope.creatorId,
    creator_name: props.posts[0]?.creator_name || props.scope.creatorId,
    source_url: `https://pawchive.pw/${props.scope.service}/user/${props.scope.creatorId}`,
  }
})
const currentIsFavorite = computed(() => props.favorites.some(x => pawchiveCreatorKey(x) === pawchiveCreatorKey(currentCreator.value)))
const search = () => {
  const query = draft.value.trim()
  validationMessage.value = query && query.length < 3 ? '搜索作者作品时，请输入至少 3 个字符。' : ''
  if (!validationMessage.value) emit('scope', { ...props.scope, query, tag: draftTag.value.trim() })
}
const applyFilters = () => emit('scope', { ...props.scope, tag: draftTag.value.trim() })
</script>

<template>
  <section class="space-y-5">
    <div class="flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div class="min-w-0">
        <h2 class="break-words text-heading font-semibold text-ink">{{ currentCreator.creator_name }}</h2>
        <p class="mt-1 text-meta text-subtle tabular-nums">{{ scope.service }} · {{ scope.creatorId }} · 已载入 {{ posts.length }} 篇 · 最新发布在前</p>
        <p v-if="currentCreator.favorite_count != null" class="mt-1 flex items-center gap-1.5 text-meta text-subtle"><Users :size="14" aria-hidden="true" />{{ currentCreator.favorite_count.toLocaleString('zh-CN') }} 人站内收藏</p>
      </div>
      <div class="flex flex-wrap items-center gap-2">
        <UiButton variant="ghost" size="sm" @click="emit('home')"><template #icon><ArrowLeft :size="14" aria-hidden="true" /></template>{{ backLabel || '返回作者' }}</UiButton>
        <UiButton size="sm" :loading="favoriteBusyKeys.includes(pawchiveCreatorKey(currentCreator))"
          :aria-label="currentIsFavorite ? `取消收藏作者 ${currentCreator.creator_name}` : `收藏作者 ${currentCreator.creator_name}`" :aria-pressed="currentIsFavorite"
          :title="accountConnected ? undefined : '登录后继续收藏'" :class="currentIsFavorite ? '!border-accent/30 !bg-accent/10 !text-accent-glow' : ''"
          @click="emit('favorite', currentCreator)"><template #icon><Heart :size="14" :fill="currentIsFavorite ? 'currentColor' : 'none'" aria-hidden="true" /></template>{{ currentIsFavorite ? '已收藏作者' : '收藏作者' }}</UiButton>
      </div>
    </div>
    <form role="search" aria-label="作者作品搜索" @submit.prevent="search">
      <div class="flex gap-2">
        <UiInput v-model="draft" type="search" class="min-w-0 flex-1" aria-label="搜索这位作者的帖子" :aria-invalid="!!validationMessage" :aria-describedby="validationMessage ? 'pawchive-post-search-error' : undefined" placeholder="搜索这位作者的帖子"><template #leading><Search :size="16" /></template></UiInput>
        <UiButton type="submit" variant="primary">搜索作品</UiButton>
      </div>
      <p :class="fieldHintClass">输入至少 3 个字符搜索作品；清空后搜索可返回全部作品。</p>
    </form>
    <p v-if="validationMessage" id="pawchive-post-search-error" role="alert" class="text-caption text-warning">{{ validationMessage }}</p>
    <div class="space-y-2 border-y border-line py-4">
      <div class="grid grid-cols-[104px_minmax(0,1fr)_auto] items-end gap-2 sm:flex sm:gap-3">
        <label class="block sm:w-32"><span :class="fieldLabelClass">媒体类型</span>
          <select :value="scope.mediaType" :disabled="!capabilities" :class="[controlClass('md'), 'select-native']" @change="emit('scope', { ...scope, mediaType: ($event.target as HTMLSelectElement).value as PawchiveScope['mediaType'] })"><option value="all">全部</option><option value="image">图片</option><option value="video">视频</option></select>
        </label>
        <label class="block min-w-0 sm:w-60"><span :class="fieldLabelClass">作者标签</span><UiInput v-model="draftTag" :disabled="!capabilities?.creator_tags" placeholder="输入标签" /></label>
        <UiButton :disabled="!capabilities?.creator_tags" @click="applyFilters">应用标签</UiButton>
      </div>
      <p class="text-caption text-subtle">媒体类型筛选作者帖子中的附件；标签由 Pawchive 按作者范围应用。</p>
    </div>
    <p v-for="warning in warnings" :key="warning" class="rounded-lg border border-warning/25 bg-warning/10 px-3.5 py-3 text-meta text-warning">{{ warning }}</p>
    <div v-if="selectedKeys.length" class="flex flex-wrap items-center justify-between gap-3 rounded-2xl border border-accent/40 bg-accent/10 py-2 pl-4 pr-2">
      <p class="text-body font-medium text-ink">已选择 <span class="tabular-nums">{{ selectedKeys.length }}</span> 篇作品</p>
      <UiButton variant="primary" :loading="downloadBusy" @click="emit('downloadSelected')">{{ downloadBusy ? '正在核对…' : '下载选中作品' }}</UiButton>
    </div>
    <p v-if="status === 'loading'" role="status" class="flex items-center justify-center gap-2 py-16 text-meta text-subtle"><UiSpinner :size="16" />正在读取作者作品…</p>
    <div v-else-if="status === 'error'" role="alert" class="rounded-2xl border border-line bg-surface"><EmptyState compact tone="danger" :icon="TriangleAlert" title="读取失败" :description="error"><UiButton size="sm" @click="emit('scope', scope)">重试</UiButton></EmptyState></div>
    <div v-else-if="status === 'ready' && posts.length === 0" class="rounded-2xl border border-dashed border-line"><EmptyState :icon="ImageOff" title="没有符合条件的作品" description="这位作者暂时没有符合条件的作品，试试调整媒体类型或标签。" /></div>
    <div v-if="posts.length" class="grid grid-cols-[repeat(auto-fill,minmax(160px,1fr))] gap-3 sm:grid-cols-[repeat(auto-fill,minmax(200px,1fr))] sm:gap-4">
      <PawchivePostCard v-for="(post, index) in posts" :key="post.post_key" :post="post" :selected="selectedKeys.includes(post.post_key)" @open="emit('open', index)" @select="emit('select', post)" />
    </div>
    <div class="flex flex-col items-center gap-2"><p v-if="error && posts.length" role="alert" class="text-meta text-danger">{{ error }}</p><UiButton v-if="hasMore" :loading="loadingMore" @click="emit('more')">{{ loadingMore ? '正在加载…' : '加载更多帖子' }}</UiButton></div>
  </section>
</template>
