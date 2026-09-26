<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Book, Eye, Film, Headphones, Image as ImageIcon, Play, Star } from 'lucide-vue-next'
import { thumbnailUrl } from '../config'
import mediaPlaceholderUrl from '../assets/media-placeholder.svg?no-inline'
import type { Media } from '../types'

const props = defineProps<{
  media: Media
  mode: 'list' | 'masonry' | 'wide'
}>()

const imageLoadFailed = ref(false)
watch(() => props.media.cover_path, () => { imageLoadFailed.value = false })

const coverUrl = computed(() =>
  imageLoadFailed.value || !props.media.cover_path
    ? mediaPlaceholderUrl
    : thumbnailUrl(props.media.cover_path)
)

const typeLabel = computed(() => {
  if (props.media.media_type === 'video') return '视频'
  if (props.media.media_type === 'manga') return '漫画'
  if (props.media.media_type === 'audio') return '音频'
  return '杂图'
})

const formatDuration = (seconds: number) => {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = total % 60
  return hours
    ? `${hours}:${String(minutes).padStart(2, '0')}:${String(rest).padStart(2, '0')}`
    : `${minutes}:${String(rest).padStart(2, '0')}`
}

const formatSize = (bytes: number) => {
  if (!bytes) return '本地目录'
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  const index = Math.min(units.length - 1, Math.floor(Math.log(bytes) / Math.log(1024)))
  return `${Number((bytes / 1024 ** index).toFixed(1))} ${units[index]}`
}

const detailText = computed(() => {
  const media = props.media
  if (media.media_type === 'manga' && media.page_count) return `${media.page_count} 页`
  if ((media.media_type === 'video' || media.media_type === 'audio') && media.duration) return formatDuration(media.duration)
  if (media.width && media.height) return `${media.width} × ${media.height}`
  return ''
})

const progressPercent = computed(() => {
  const media = props.media
  if (media.media_type === 'video' && media.duration && media.progress > 0) {
    return Math.min(100, Math.max(0, Math.round(media.progress / media.duration * 100)))
  }
  if (media.media_type === 'manga' && media.page_count && media.progress >= 0) {
    return Math.min(100, Math.max(0, Math.round((media.progress + 1) / media.page_count * 100)))
  }
  return 0
})

const imageAspect = computed(() => {
  const media = props.media
  return media.media_type === 'image' && media.width && media.height
    ? { aspectRatio: `${media.width} / ${media.height}` }
    : undefined
})
</script>

<template>
  <button
    v-if="mode === 'list'"
    type="button"
    class="group flex w-full items-center gap-3 sm:gap-4 rounded-xl border border-white/8 bg-white/[0.025] p-2.5 text-left transition-colors hover:border-white/20 hover:bg-white/[0.055] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    :aria-label="media.title"
  >
    <div class="relative h-20 w-16 shrink-0 overflow-hidden rounded-lg bg-white/5 sm:h-24 sm:w-20">
      <img :src="coverUrl" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover" @error="imageLoadFailed = true" />
      <div v-if="progressPercent" class="absolute inset-x-0 bottom-0 h-1 bg-black/50">
        <div class="h-full bg-accent" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>
    <div class="min-w-0 flex-1 py-0.5">
      <div class="flex flex-wrap items-center gap-1.5 text-[10px] font-bold text-white/45">
        <span>{{ typeLabel }}</span>
        <span v-if="media.is_missing" class="text-red-300">文件丢失</span>
        <span v-if="media.favorite" class="inline-flex items-center gap-0.5 text-amber-300"><Star :size="11" fill="currentColor" /> 收藏</span>
        <span v-if="media.view_status === 'viewed'" class="inline-flex items-center gap-0.5 text-emerald-300"><Eye :size="11" /> 已看</span>
      </div>
      <h3 class="mt-1 break-words text-sm font-bold leading-snug text-white/90 group-hover:text-accent">{{ media.title }}</h3>
      <div class="mt-1.5 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-xs text-white/45">
        <span>{{ media.extension.replace('.', '').toUpperCase() || 'DIR' }}</span>
        <span v-if="detailText">{{ detailText }}</span>
        <span>{{ formatSize(media.file_size) }}</span>
        <span v-if="progressPercent">已看 {{ progressPercent }}%</span>
        <span v-if="media.rating" class="inline-flex items-center gap-0.5 text-amber-300"><Star :size="11" fill="currentColor" />{{ media.rating }}</span>
      </div>
    </div>
  </button>

  <button
    v-else-if="mode === 'masonry'"
    type="button"
    class="group w-full overflow-hidden rounded-xl border border-white/8 bg-white/[0.025] text-left transition-colors hover:border-white/20 hover:bg-white/[0.055] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    :aria-label="media.title"
  >
    <div class="relative w-full overflow-hidden bg-white/5">
      <img :src="coverUrl" alt="" loading="lazy" decoding="async" class="block w-full h-auto" :style="imageAspect" @error="imageLoadFailed = true" />
      <div class="absolute top-2 right-2 rounded-md bg-black/70 px-1.5 py-0.5 text-[10px] font-bold text-white/85">{{ typeLabel }}</div>
      <Star v-if="media.favorite" :size="16" fill="currentColor" class="absolute top-2 left-2 rounded bg-black/70 p-0.5 text-amber-300" />
      <div v-if="progressPercent" class="absolute inset-x-0 bottom-0 h-1 bg-black/50">
        <div class="h-full bg-accent" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>
    <div class="px-3 py-2.5">
      <h3 class="line-clamp-2 text-sm font-bold leading-snug text-white/90 group-hover:text-accent" :title="media.title">{{ media.title }}</h3>
      <div class="mt-1.5 flex items-center gap-2 text-[11px] text-white/45">
        <span v-if="detailText">{{ detailText }}</span>
        <span v-if="media.rating" class="ml-auto inline-flex items-center gap-0.5 text-amber-300"><Star :size="11" fill="currentColor" />{{ media.rating }}</span>
        <span v-if="media.is_missing" class="ml-auto text-red-300">文件丢失</span>
      </div>
    </div>
  </button>

  <button
    v-else
    type="button"
    class="group w-full overflow-hidden rounded-2xl border border-white/8 bg-white/[0.025] text-left transition-colors hover:border-white/20 hover:bg-white/[0.055] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent/50"
    :aria-label="media.title"
  >
    <div class="relative aspect-video w-full overflow-hidden bg-white/5">
      <img :src="coverUrl" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]" @error="imageLoadFailed = true" />
      <div class="absolute inset-0 flex items-center justify-center bg-black/10 opacity-0 transition-opacity group-hover:opacity-100">
        <span class="flex h-12 w-12 items-center justify-center rounded-full border border-white/30 bg-black/65 text-white"><Play :size="20" fill="currentColor" /></span>
      </div>
      <span v-if="media.duration" class="absolute right-2 bottom-3 rounded-md bg-black/80 px-1.5 py-0.5 text-[11px] font-bold text-white">{{ formatDuration(media.duration) }}</span>
      <span v-if="media.is_missing" class="absolute top-2 right-2 rounded-md bg-red-500/90 px-1.5 py-0.5 text-[11px] font-bold text-white">文件丢失</span>
      <span v-if="media.favorite" class="absolute top-2 left-2 rounded-md bg-black/75 p-1 text-amber-300"><Star :size="13" fill="currentColor" /></span>
      <div v-if="progressPercent" class="absolute inset-x-0 bottom-0 h-1 bg-black/50">
        <div class="h-full bg-accent" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>
    <div class="p-3">
      <h3 class="line-clamp-2 min-h-10 text-sm font-bold leading-snug text-white/90 group-hover:text-accent" :title="media.title">{{ media.title }}</h3>
      <div class="mt-2 flex items-center gap-2 text-[11px] text-white/45">
        <Film v-if="media.media_type === 'video'" :size="12" />
        <Book v-else-if="media.media_type === 'manga'" :size="12" />
        <Headphones v-else-if="media.media_type === 'audio'" :size="12" />
        <ImageIcon v-else :size="12" />
        <span>{{ typeLabel }}</span>
        <span v-if="progressPercent">已看 {{ progressPercent }}%</span>
        <span v-if="media.rating" class="ml-auto inline-flex items-center gap-0.5 text-amber-300"><Star :size="11" fill="currentColor" />{{ media.rating }}</span>
      </div>
    </div>
  </button>
</template>
