<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { Book, Check, Film, Headphones, Image as ImageIcon, Star } from 'lucide-vue-next'
import { thumbnailUrl } from '../config'
import mediaPlaceholderUrl from '../assets/media-placeholder.svg?no-inline'
import type { Media } from '../types'

const props = withDefaults(defineProps<{
  media: Media
  index?: number
  eager?: boolean
  virtualized?: boolean
  /**
   * poster: uniform 2:3 tile for mixed walls; 16:9 / square art is shown whole
   * on a blurred backdrop instead of being cropped.
   * natural: the tile takes the media type's own aspect (video 16:9, audio 1:1,
   * manga 2:3, image its real ratio), for single-type grids.
   */
  shape?: 'poster' | 'natural'
  /** Show the type badge (turn off on single-type pages). */
  showType?: boolean
}>(), {
  index: 0,
  eager: false,
  virtualized: false,
  shape: 'poster',
  showType: true,
})

const imageLoadFailed = ref(false)
const onImageError = () => {
  imageLoadFailed.value = true
}

watch(() => props.media.cover_path, () => {
  imageLoadFailed.value = false
})

const getThumb = (path: string | null) => path ? thumbnailUrl(path) : mediaPlaceholderUrl
const coverSrc = computed(() => imageLoadFailed.value ? mediaPlaceholderUrl : getThumb(props.media.cover_path))

const formatSize = (bytes: number) => {
  if (bytes === 0) return '本地目录'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

const formatDuration = (seconds: number) => {
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = String(total % 60).padStart(2, '0')
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}

const progressPercent = (media: Media) => {
  if (media.media_type === 'video' && media.duration && media.progress > 0) {
    return Math.min(100, Math.max(0, Math.round((media.progress / media.duration) * 100)))
  }

  // Manga progress is a 0-based page index, so page 0 only counts once reading started.
  if (media.media_type === 'manga' && media.page_count && media.progress >= 0 && media.view_status !== 'unviewed') {
    return Math.min(100, Math.max(0, Math.round(((media.progress + 1) / media.page_count) * 100)))
  }

  return 0
}

const mangaProgressText = (media: Media) => {
  if (media.media_type !== 'manga' || !media.page_count) return ''
  const current = Math.min(media.page_count, Math.max(1, media.progress + 1))
  return `${current}/${media.page_count}`
}

const formatMeta = (media: Media) => {
  if (media.media_type === 'video') {
    const percent = progressPercent(media)
    return percent > 0 ? `已看 ${percent}%` : formatSize(media.file_size)
  }
  if (media.media_type === 'manga' && media.page_count) {
    return progressPercent(media) > 0 ? `${mangaProgressText(media)} 页` : `${media.page_count} 页`
  }
  if (media.width && media.height) return `${media.width}×${media.height}`
  return formatSize(media.file_size)
}

const typeLabel = (type: Media['media_type']) => {
  if (type === 'video') return '视频'
  if (type === 'manga') return '漫画'
  if (type === 'audio') return '音频'
  return '杂图'
}

const percent = computed(() => progressPercent(props.media))
const extension = computed(() => props.media.extension.replace('.', '').toUpperCase() || 'DIR')
const showDuration = computed(() => (props.media.media_type === 'video' || props.media.media_type === 'audio') && !!props.media.duration)

// Video stills and album art are not 2:3; fit them whole inside a poster tile.
const contained = computed(() => props.shape === 'poster' && (props.media.media_type === 'video' || props.media.media_type === 'audio'))

const frameStyle = computed(() => {
  if (props.shape === 'poster') return { aspectRatio: '2 / 3' }
  const media = props.media
  if (media.media_type === 'video') return { aspectRatio: '16 / 9' }
  if (media.media_type === 'audio') return { aspectRatio: '1 / 1' }
  if (media.media_type === 'image' && media.width && media.height) {
    return { aspectRatio: String(Math.min(2, Math.max(0.5, media.width / media.height))) }
  }
  return { aspectRatio: '2 / 3' }
})
</script>

<template>
  <button
    type="button"
    :style="{ animationDelay: `${Math.min(24, index) * 30}ms` }"
    :class="{
      'animate-fluid-entrance': !virtualized && index < 16,
      'virtual-card': virtualized,
    }"
    class="he-media-card lazy-card tap-active group relative flex w-full flex-col rounded-2xl text-left focus:outline-none"
  >
    <div
      class="he-media-card__frame relative w-full overflow-hidden rounded-2xl bg-surface-2 transition-shadow duration-200 ease-out group-focus-visible:ring-2 group-focus-visible:ring-accent group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background"
      :style="frameStyle"
    >
      <img
        v-if="contained"
        :src="coverSrc"
        alt=""
        aria-hidden="true"
        :loading="eager || !virtualized || index < 36 ? 'eager' : 'lazy'"
        decoding="async"
        class="he-media-card__backdrop absolute inset-0 h-full w-full object-cover"
      />
      <img
        :src="coverSrc"
        :alt="media.title"
        :loading="eager || !virtualized || index < 36 ? 'eager' : 'lazy'"
        decoding="async"
        class="he-media-card__art absolute inset-0 h-full w-full"
        :class="contained ? 'object-contain' : 'object-cover'"
        @error="onImageError"
      />

      <!-- Bottom scrim keeps overlay badges readable on bright art. -->
      <div class="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/45 to-transparent"></div>
      <div class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/8 transition-colors duration-200 group-hover:ring-white/20"></div>

      <div v-if="media.favorite" class="absolute left-2 top-2 grid size-6 place-items-center rounded-md bg-black/60 text-star" title="已收藏">
        <Star :size="13" fill="currentColor" aria-hidden="true" />
        <span class="sr-only">已收藏</span>
      </div>

      <div v-if="showType" class="absolute right-2 top-2 inline-flex h-6 items-center gap-1 rounded-md bg-black/60 px-1.5 text-caption font-medium text-white/90">
        <Film v-if="media.media_type === 'video'" :size="12" aria-hidden="true" />
        <Book v-else-if="media.media_type === 'manga'" :size="12" aria-hidden="true" />
        <Headphones v-else-if="media.media_type === 'audio'" :size="12" aria-hidden="true" />
        <ImageIcon v-else :size="12" aria-hidden="true" />
        <span>{{ typeLabel(media.media_type) }}</span>
      </div>

      <div v-if="media.is_missing" class="absolute bottom-2.5 left-2 inline-flex h-6 items-center rounded-md bg-danger px-1.5 text-caption font-semibold text-black/85">
        文件丢失
      </div>

      <span v-if="showDuration" class="absolute bottom-2.5 right-2 inline-flex h-6 items-center rounded-md bg-black/70 px-1.5 text-caption font-medium tabular-nums text-white">
        {{ formatDuration(media.duration!) }}
      </span>

      <div v-if="percent > 0" class="absolute inset-x-0 bottom-0 h-[3px] bg-black/45" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100" :aria-label="`进度 ${percent}%`">
        <div class="h-full bg-accent" :style="{ width: `${percent}%` }"></div>
      </div>
    </div>

    <div class="mt-2.5 w-full min-w-0 px-0.5">
      <h3 class="line-clamp-2 min-h-[2.75em] text-meta font-medium leading-snug text-ink sm:text-body sm:leading-snug" :title="media.title">
        {{ media.title }}
      </h3>
      <div class="mt-1 flex min-w-0 items-center gap-1.5 text-caption text-subtle tabular-nums">
        <span class="shrink-0 font-medium text-muted">{{ extension }}</span>
        <span class="shrink-0 text-faint" aria-hidden="true">·</span>
        <span class="truncate">{{ formatMeta(media) }}</span>

        <span v-if="media.rating" class="ml-auto inline-flex shrink-0 items-center gap-0.5 font-medium text-star" :title="`评分: ${media.rating} 星`">
          <Star :size="11" fill="currentColor" aria-hidden="true" />
          <span>{{ media.rating }}</span>
        </span>

        <span v-if="media.view_status === 'viewed'" class="shrink-0 text-success" :class="{ 'ml-auto': !media.rating }" title="已看">
          <Check :size="13" :stroke-width="2.5" aria-hidden="true" />
          <span class="sr-only">已看</span>
        </span>
      </div>
    </div>
  </button>
</template>

<style>
.he-media-card__backdrop {
  transform: scale(1.25);
  filter: blur(16px) saturate(1.2) brightness(0.55);
}

.he-media-card__art {
  transition: transform var(--duration-slow) var(--ease-out);
}

@media (hover: hover) {
  .he-media-card:hover .he-media-card__art {
    transform: scale(1.03);
  }
}
</style>
