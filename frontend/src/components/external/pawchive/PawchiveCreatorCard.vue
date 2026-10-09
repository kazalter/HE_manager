<script setup lang="ts">
import { computed, ref } from 'vue'
import { CalendarDays, Heart, UserRound } from 'lucide-vue-next'
import { iconButtonClass } from '../../ui'
import type { PawchiveCreator, PawchivePost } from '../../../types/pawchive'

const props = defineProps<{
  creator: PawchiveCreator
  latestPost?: PawchivePost | null
  postCount?: number
  favorite: boolean
  busy?: boolean
  canFavorite?: boolean
}>()

const emit = defineEmits<{
  open: []
  favorite: []
}>()
const bannerFailed = ref(false)
const iconFailed = ref(false)
const bannerUrl = computed(() => props.creator.banner_url ||
  `https://pawchive.pw/banners/${encodeURIComponent(props.creator.service)}/${encodeURIComponent(props.creator.creator_id)}`)
const iconUrl = computed(() => props.creator.icon_url ||
  `https://pawchive.pw/icons/${encodeURIComponent(props.creator.service)}/${encodeURIComponent(props.creator.creator_id)}`)
const serviceName = computed(() => ({ fanbox: 'Fanbox', patreon: 'Patreon', discord: 'Discord', fantia: 'Fantia', gumroad: 'Gumroad' }[props.creator.service] || props.creator.service))
const updateLabel = computed(() => {
  const value = props.creator.updated_at || props.latestPost?.published_at
  if (!value) return '暂无更新时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '暂无更新时间'
  return `更新 ${new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)}`
})
</script>

<template>
  <article class="group flex min-w-0 flex-col overflow-hidden rounded-2xl border border-line bg-surface transition-colors duration-150 hover:border-line-strong">
    <button type="button" class="block w-full min-w-0 text-left focus-ring-inset" :aria-label="`查看作者 ${creator.creator_name}`" @click="emit('open')">
      <div class="relative aspect-[2.15/1] overflow-hidden bg-surface-2">
        <img v-if="!bannerFailed" :src="bannerUrl" alt="" loading="lazy" class="h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.03]" @error="bannerFailed = true" />
        <div class="pointer-events-none absolute inset-x-0 bottom-0 h-1/2 bg-gradient-to-t from-black/45 to-transparent" aria-hidden="true"></div>
        <span class="absolute right-2 top-2 inline-flex h-6 items-center rounded-md bg-black/60 px-1.5 text-caption font-medium text-white/90">{{ serviceName }}</span>
        <div class="absolute bottom-2 left-3 flex size-11 items-center justify-center overflow-hidden rounded-lg bg-surface-3 ring-2 ring-black/40">
          <img v-if="!iconFailed" :src="iconUrl" alt="" loading="lazy" class="h-full w-full object-cover" @error="iconFailed = true" />
          <UserRound v-else :size="20" class="text-subtle" aria-hidden="true" />
        </div>
      </div>
      <div class="px-3 pb-2 pt-3">
        <h4 class="truncate text-body font-medium text-ink" :title="creator.creator_name || creator.creator_id">{{ creator.creator_name || creator.creator_id }}</h4>
        <p class="mt-0.5 truncate text-meta text-subtle" :title="creator.creator_id">{{ creator.creator_id }}<span v-if="postCount" class="tabular-nums"> · {{ postCount }} 篇匹配</span></p>
        <p v-if="latestPost" class="mt-0.5 truncate text-meta text-muted" :title="latestPost.title || '无标题帖子'">{{ latestPost.title || '无标题帖子' }}</p>
      </div>
    </button>
    <div class="mt-auto flex items-center justify-between gap-1 py-1 pl-3 pr-1.5">
      <p class="flex min-w-0 items-center gap-1.5 truncate text-caption text-subtle tabular-nums" :title="updateLabel"><CalendarDays :size="13" class="shrink-0" aria-hidden="true" />{{ updateLabel }}</p>
      <button
        type="button"
        :disabled="busy || !canFavorite"
        :class="[iconButtonClass('ghost', 'md'), favorite ? 'text-accent-glow' : '']"
        :aria-label="favorite ? `取消收藏作者 ${creator.creator_name}` : `收藏作者 ${creator.creator_name}`"
        :aria-pressed="favorite"
        :title="canFavorite ? (favorite ? '取消收藏作者' : '收藏作者') : '登录 Pawchive 账号后可收藏作者'"
        @click="emit('favorite')"
      ><Heart :size="18" :fill="favorite ? 'currentColor' : 'none'" aria-hidden="true" /></button>
    </div>
  </article>
</template>
