<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUpRight, CalendarDays, Heart, UserRound } from 'lucide-vue-next'
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
const serviceName = computed(() => ({ fanbox: 'FANBOX', patreon: 'PATREON', discord: 'DISCORD' }[props.creator.service] || props.creator.service.toUpperCase()))
const updateLabel = computed(() => {
  const value = props.creator.updated_at || props.latestPost?.published_at
  if (!value) return '暂无更新时间'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return '暂无更新时间'
  return `更新 ${new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: '2-digit', day: '2-digit' }).format(date)}`
})
</script>

<template>
  <article class="group flex min-w-0 flex-col overflow-hidden rounded-2xl border border-white/10 bg-white/[0.045] shadow-lg shadow-black/10 transition-[border-color,box-shadow,transform] duration-200 hover:border-accent/50 hover:shadow-accent/10 motion-safe:hover:-translate-y-0.5">
    <button type="button" class="block w-full min-w-0 text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent" :aria-label="`查看作者 ${creator.creator_name}`" @click="emit('open')">
      <div class="relative aspect-[2.15/1] overflow-hidden bg-gradient-to-br from-accent/25 via-white/10 to-black/45">
        <img v-if="!bannerFailed" :src="bannerUrl" alt="" loading="lazy" class="h-full w-full object-cover transition-transform duration-300 motion-safe:group-hover:scale-105" @error="bannerFailed = true" />
        <div class="absolute inset-0 bg-gradient-to-t from-black/75 via-transparent to-black/20" aria-hidden="true"></div>
        <span class="absolute right-2 top-2 rounded-md border border-white/20 bg-black/55 px-2 py-1 text-[10px] font-bold tracking-wider text-white backdrop-blur-sm">{{ serviceName }}</span>
        <div class="absolute -bottom-0 left-3 flex h-11 w-11 items-center justify-center overflow-hidden rounded-xl border-2 border-white/70 bg-zinc-900 shadow-lg shadow-black/40">
          <img v-if="!iconFailed" :src="iconUrl" alt="" loading="lazy" class="h-full w-full object-cover" @error="iconFailed = true" />
          <UserRound v-else :size="20" class="text-white/75" aria-hidden="true" />
        </div>
      </div>
      <div class="min-h-20 px-3 pb-2 pt-3">
        <div class="flex min-w-0 items-start justify-between gap-1">
          <h4 class="line-clamp-1 min-w-0 break-words text-sm font-bold text-white" :title="creator.creator_name || creator.creator_id">{{ creator.creator_name || creator.creator_id }}</h4>
          <ArrowUpRight :size="15" class="shrink-0 text-white/45 transition-colors group-hover:text-accent" aria-hidden="true" />
        </div>
        <p class="mt-1 truncate text-xs text-white/60" :title="creator.creator_id">{{ creator.creator_id }}<span v-if="postCount"> · {{ postCount }} 篇匹配</span></p>
        <p v-if="latestPost" class="mt-1 line-clamp-1 text-xs text-white/65" :title="latestPost.title || '无标题帖子'">{{ latestPost.title || '无标题帖子' }}</p>
      </div>
    </button>
    <div class="mt-auto flex items-center justify-between gap-1 border-t border-white/10 px-3 py-2">
      <p class="flex min-w-0 items-center gap-1 truncate text-xs text-white/70" :title="updateLabel"><CalendarDays :size="13" class="shrink-0 text-accent/80" aria-hidden="true" />{{ updateLabel }}</p>
      <button type="button" :disabled="busy || !canFavorite" class="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl transition-colors cursor-pointer disabled:opacity-50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" :class="favorite ? 'bg-pink-300/15 text-pink-200 hover:bg-pink-300/25' : 'bg-white/10 text-white/75 hover:bg-accent/20 hover:text-white'" :aria-label="favorite ? `取消收藏作者 ${creator.creator_name}` : `收藏作者 ${creator.creator_name}`" :aria-pressed="favorite" :title="canFavorite ? (favorite ? '取消收藏作者' : '收藏作者') : '登录 Pawchive 账号后可收藏作者'" @click="emit('favorite')"><Heart :size="18" :fill="favorite ? 'currentColor' : 'none'" aria-hidden="true" /></button>
    </div>
  </article>
</template>
