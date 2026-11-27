<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Book, Check, Film, Headphones, Image as ImageIcon, Play, Star } from 'lucide-vue-next'
import { thumbnailUrl } from '../config'
import mediaPlaceholderUrl from '../assets/media-placeholder.svg?no-inline'
import type { Media } from '../types'

const props = defineProps<{
  media: Media
  mode: 'list' | 'masonry' | 'wide'
}>()

const imageLoadFailed = ref(false)
const imageRetried = ref(false)
const onImageError = () => {
  if (props.media.cover_path && !imageRetried.value) {
    imageRetried.value = true
    return
  }
  imageLoadFailed.value = true
}
watch(() => props.media.cover_path, () => {
  imageLoadFailed.value = false
  imageRetried.value = false
})

const coverUrl = computed(() =>
  imageLoadFailed.value || !props.media.cover_path
    ? mediaPlaceholderUrl
    : thumbnailUrl(props.media.cover_path, imageRetried.value)
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
  // Manga progress is a 0-based page index, so page 0 only counts once reading started.
  if (media.media_type === 'manga' && media.page_count && media.progress >= 0 && media.view_status !== 'unviewed') {
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
    class="group flex w-full items-center gap-3 rounded-2xl border border-line/65 bg-surface/55 p-2 pr-4 text-left backdrop-blur-md shadow-[inset_0_1px_0_var(--he-border-specular)] transition-[background-color,border-color,box-shadow] duration-150 ease-out hover:border-accent/35 hover:bg-surface-2/75 hover:shadow-[var(--he-shadow-card)] focus-ring sm:gap-4"
    :aria-label="media.title"
  >
    <div class="relative h-[72px] w-12 shrink-0 overflow-hidden rounded-xl bg-surface-2 ring-1 ring-inset ring-white/10 sm:h-20 sm:w-[54px]">
      <img :src="coverUrl" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover transition-transform duration-200 group-hover:scale-105" @error="onImageError" />
      <div v-if="progressPercent" class="absolute inset-x-0 bottom-0 h-[3px] bg-black/50">
        <div class="h-full bg-gradient-to-r from-accent to-accent-glow" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>
    <div class="min-w-0 flex-1">
      <h3 class="line-clamp-2 break-words text-body font-medium leading-snug text-ink transition-colors group-hover:text-accent-glow">{{ media.title }}</h3>
      <div class="mt-1.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-caption text-subtle tabular-nums">
        <span class="rounded-md border border-line/55 bg-surface-2/75 px-1.5 py-px font-medium text-muted">{{ typeLabel }}</span>
        <span>{{ media.extension.replace('.', '').toUpperCase() || 'DIR' }}</span>
        <template v-if="detailText"><span class="text-faint" aria-hidden="true">·</span><span>{{ detailText }}</span></template>
        <span class="text-faint" aria-hidden="true">·</span>
        <span>{{ formatSize(media.file_size) }}</span>
        <template v-if="progressPercent"><span class="text-faint" aria-hidden="true">·</span><span class="text-accent-glow">已看 {{ progressPercent }}%</span></template>
      </div>
    </div>
    <div class="flex shrink-0 items-center gap-2 text-caption tabular-nums">
      <span v-if="media.is_missing" class="rounded-full bg-danger/15 px-2 py-0.5 font-medium text-danger">文件丢失</span>
      <span v-if="media.view_status === 'viewed'" class="text-success" title="已看"><Check :size="14" :stroke-width="2.5" aria-hidden="true" /><span class="sr-only">已看</span></span>
      <span v-if="media.favorite" class="text-star" title="收藏"><Star :size="14" fill="currentColor" aria-hidden="true" /><span class="sr-only">收藏</span></span>
      <span v-if="media.rating" class="inline-flex items-center gap-0.5 font-medium text-star"><Star :size="11" fill="currentColor" aria-hidden="true" />{{ media.rating }}</span>
    </div>
  </button>

  <button
    v-else-if="mode === 'masonry'"
    type="button"
    class="tap-active group w-full overflow-hidden rounded-2xl bg-surface/65 text-left backdrop-blur-md ring-1 ring-inset ring-line/70 shadow-[var(--he-shadow-card)] transition-[transform,box-shadow] duration-200 ease-out hover:-translate-y-1 hover:ring-accent/40 hover:shadow-[var(--he-shadow-card-hover)] focus-ring"
    :aria-label="media.title"
  >
    <div class="relative w-full overflow-hidden bg-surface-2">
      <img :src="coverUrl" alt="" loading="lazy" decoding="async" class="block h-auto w-full transition-transform duration-200 ease-out group-hover:scale-[1.035]" :style="imageAspect" @error="onImageError" />
      <div class="he-card-type-badge he-glass-pill absolute right-2 top-2 inline-flex min-h-6 items-center rounded-full px-2 py-0.5 text-[11px] font-medium text-white/92">{{ typeLabel }}</div>
      <span v-if="media.favorite" class="he-glass-pill absolute left-2 top-2 grid size-6 place-items-center rounded-full text-star shadow-[0_0_12px_rgb(var(--color-star)/0.38)]"><Star :size="12" fill="currentColor" aria-hidden="true" /></span>
      <div v-if="progressPercent" class="absolute inset-x-0 bottom-0 h-[3px] bg-black/50">
        <div class="h-full bg-gradient-to-r from-accent to-accent-glow" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>
    <div class="px-3 py-2.5">
      <h3 class="line-clamp-2 text-meta font-medium leading-snug text-ink transition-colors group-hover:text-accent-glow" :title="media.title">{{ media.title }}</h3>
      <div class="mt-1 flex items-center gap-2 text-caption text-subtle tabular-nums">
        <span v-if="detailText">{{ detailText }}</span>
        <span v-if="media.rating" class="ml-auto inline-flex items-center gap-0.5 font-medium text-star"><Star :size="11" fill="currentColor" aria-hidden="true" />{{ media.rating }}</span>
        <span v-if="media.is_missing" class="ml-auto font-medium text-danger">文件丢失</span>
      </div>
    </div>
  </button>

  <button
    v-else
    type="button"
    class="group w-full text-left focus:outline-none"
    :aria-label="media.title"
  >
    <div class="relative aspect-video w-full overflow-hidden rounded-2xl bg-surface-2 shadow-[var(--he-shadow-card)] transition-[transform,box-shadow] duration-200 ease-out group-hover:-translate-y-1 group-hover:shadow-[var(--he-shadow-card-hover)] group-focus-visible:ring-2 group-focus-visible:ring-accent group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background">
      <img :src="coverUrl" alt="" loading="lazy" decoding="async" class="h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.035]" @error="onImageError" />
      <div class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/12 transition-colors group-hover:ring-accent/45"></div>
      <div class="absolute inset-0 flex items-center justify-center opacity-0 transition-opacity duration-150 group-hover:opacity-100 group-focus-visible:opacity-100">
        <span class="he-glass-capsule grid size-12 place-items-center rounded-full text-white"><Play :size="20" fill="currentColor" aria-hidden="true" /></span>
      </div>
      <span v-if="media.duration" class="he-glass-pill absolute bottom-2.5 right-2 inline-flex min-h-5 items-center rounded-full px-2 py-0.5 text-[11px] font-medium tabular-nums text-white/95">{{ formatDuration(media.duration) }}</span>
      <span v-if="media.is_missing" class="absolute bottom-2.5 left-2 inline-flex min-h-6 items-center rounded-full bg-danger/90 px-2 py-0.5 text-[11px] font-semibold text-black/90">文件丢失</span>
      <span v-if="media.favorite" class="he-glass-pill absolute left-2 top-2 grid size-6 place-items-center rounded-full text-star shadow-[0_0_12px_rgb(var(--color-star)/0.38)]"><Star :size="12" fill="currentColor" aria-hidden="true" /></span>
      <div v-if="progressPercent" class="absolute inset-x-0 bottom-0 h-[3px] bg-black/45">
        <div class="h-full bg-gradient-to-r from-accent to-accent-glow shadow-[0_0_10px_rgb(var(--color-accent)/0.9)]" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </div>
    <div class="mt-2.5 px-0.5">
      <h3 class="line-clamp-2 min-h-[2.75em] text-body font-medium leading-snug text-ink transition-colors group-hover:text-accent-glow" :title="media.title">{{ media.title }}</h3>
      <div class="mt-1 flex items-center gap-1.5 text-caption text-subtle tabular-nums">
        <Film v-if="media.media_type === 'video'" :size="12" aria-hidden="true" />
        <Book v-else-if="media.media_type === 'manga'" :size="12" aria-hidden="true" />
        <Headphones v-else-if="media.media_type === 'audio'" :size="12" aria-hidden="true" />
        <ImageIcon v-else :size="12" aria-hidden="true" />
        <span>{{ typeLabel }}</span>
        <template v-if="progressPercent"><span class="text-faint" aria-hidden="true">·</span><span class="text-accent-glow">已看 {{ progressPercent }}%</span></template>
        <span v-if="media.rating" class="ml-auto inline-flex items-center gap-0.5 font-medium text-star"><Star :size="11" fill="currentColor" aria-hidden="true" />{{ media.rating }}</span>
      </div>
    </div>
  </button>
</template>
