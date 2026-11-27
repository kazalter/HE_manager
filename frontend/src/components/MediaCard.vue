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

const getThumb = (path: string | null) => path ? thumbnailUrl(path, imageRetried.value) : mediaPlaceholderUrl
const coverSrc = computed(() => imageLoadFailed.value ? mediaPlaceholderUrl : getThumb(props.media.cover_path))

const formatSize = (bytes: number) => {
  if (!bytes || bytes <= 0) return bytes === 0 ? '本地目录' : '0 B'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(k)), sizes.length - 1)
  if (i < 0) return `${bytes} B`
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

const formatDuration = (seconds: number) => {
  if (!seconds || seconds <= 0 || !Number.isFinite(seconds)) return '0:00'
  const total = Math.max(0, Math.floor(seconds))
  const hours = Math.floor(total / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const rest = String(total % 60).padStart(2, '0')
  return hours ? `${hours}:${String(minutes).padStart(2, '0')}:${rest}` : `${minutes}:${rest}`
}

const progressPercent = (media: Media) => {
  if (media.media_type === 'video' && media.duration && media.duration > 0 && media.progress > 0) {
    return Math.min(100, Math.max(0, Math.round((media.progress / media.duration) * 100)))
  }

  // Manga progress is a 0-based page index, so page 0 only counts once reading started.
  if (media.media_type === 'manga' && media.page_count && media.page_count > 0 && media.progress >= 0 && media.view_status !== 'unviewed') {
    return Math.min(100, Math.max(0, Math.round(((media.progress + 1) / media.page_count) * 100)))
  }

  return 0
}

const mangaProgressText = (media: Media) => {
  if (media.media_type !== 'manga' || !media.page_count || media.page_count <= 0) return ''
  const current = Math.min(media.page_count, Math.max(1, (media.progress ?? 0) + 1))
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
const extension = computed(() => props.media.extension ? props.media.extension.replace('.', '').toUpperCase() : 'DIR')
const showDuration = computed(() => (props.media.media_type === 'video' || props.media.media_type === 'audio') && !!props.media.duration)

// Video stills and album art are not 2:3; fit them whole inside a poster tile.
const contained = computed(() => props.shape === 'poster' && (props.media.media_type === 'video' || props.media.media_type === 'audio'))
const imageLoading = computed(() => (props.eager || props.index < 12 ? 'eager' : 'lazy'))
const imagePriority = computed(() => (props.index < 4 ? 'high' : undefined))

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
    :data-media-id="media.id"
    :class="{
      'virtual-card': virtualized,
    }"
    class="he-media-card lazy-card tap-active group relative flex w-full flex-col rounded-2xl text-left focus:outline-none"
  >
    <div
      class="he-media-card__frame relative w-full overflow-hidden rounded-2xl bg-surface-2 transition-transform duration-200 ease-out group-focus-visible:ring-2 group-focus-visible:ring-accent group-focus-visible:ring-offset-2 group-focus-visible:ring-offset-background"
      :style="frameStyle"
    >
      <img
        v-if="contained"
        :src="coverSrc"
        alt=""
        aria-hidden="true"
        :loading="imageLoading"
        decoding="async"
        class="he-media-card__backdrop absolute inset-0 h-full w-full object-cover"
      />
      <img
        :src="coverSrc"
        :alt="media.title"
        :loading="imageLoading"
        :fetchpriority="imagePriority"
        decoding="async"
        class="he-media-card__art absolute inset-0 h-full w-full"
        :class="contained ? 'object-contain' : 'object-cover'"
        @error="onImageError"
      />

      <!-- Subtle bottom vignette keeps duration and progress legible without dulling artwork. -->
      <div class="pointer-events-none absolute inset-x-0 bottom-0 h-1/3 bg-gradient-to-t from-black/62 via-black/14 to-transparent"></div>
      <div class="pointer-events-none absolute inset-0 rounded-2xl ring-1 ring-inset ring-white/12 transition-colors duration-200 group-hover:ring-accent/45"></div>

      <div v-if="media.favorite" class="he-glass-pill absolute left-2 top-2 grid size-6 place-items-center rounded-full text-star shadow-[0_0_12px_rgb(var(--color-star)/0.38)]" title="已收藏">
        <Star :size="12" fill="currentColor" aria-hidden="true" />
        <span class="sr-only">已收藏</span>
      </div>

      <div v-if="showType" class="he-card-type-badge he-glass-pill absolute right-2 top-2 inline-flex min-h-6 items-center gap-1 rounded-full px-2 py-0.5 text-[11px] font-medium text-white/92">
        <Film v-if="media.media_type === 'video'" :size="11" aria-hidden="true" />
        <Book v-else-if="media.media_type === 'manga'" :size="11" aria-hidden="true" />
        <Headphones v-else-if="media.media_type === 'audio'" :size="11" aria-hidden="true" />
        <ImageIcon v-else :size="11" aria-hidden="true" />
        <span>{{ typeLabel(media.media_type) }}</span>
      </div>

      <div v-if="media.is_missing" class="he-badge-missing absolute bottom-2.5 left-2 inline-flex min-h-6 items-center rounded-full bg-danger/90 px-2 py-0.5 text-[11px] font-semibold text-black/90 shadow-sm">
        文件丢失
      </div>

      <span v-if="showDuration" class="he-card-duration he-glass-pill absolute bottom-2.5 right-2 inline-flex min-h-5 items-center rounded-full px-2 py-0.5 text-[11px] font-medium tabular-nums text-white/95 transition-[bottom] duration-150">
        {{ formatDuration(media.duration!) }}
      </span>

      <div v-if="percent > 0" class="absolute inset-x-0 bottom-0 h-[3px] bg-black/45" role="progressbar" :aria-valuenow="percent" aria-valuemin="0" aria-valuemax="100" :aria-label="`进度 ${percent}%`">
        <div class="h-full bg-gradient-to-r from-accent to-accent-glow shadow-[0_0_10px_rgb(var(--color-accent)/0.9)]" :style="{ width: `${percent}%` }"></div>
      </div>
    </div>

    <div class="he-media-card__body mt-2.5 w-full min-w-0 px-0.5">
      <h3 class="line-clamp-2 min-h-[2.75em] wrap-anywhere text-meta font-medium leading-snug text-ink transition-colors duration-150 group-hover:text-accent-glow sm:text-body sm:leading-snug" :title="media.title">
        {{ media.title }}
      </h3>
      <div class="mt-1 flex min-w-0 items-center gap-1.5 text-caption text-subtle tabular-nums">
        <span class="shrink-0 rounded-md border border-line/55 bg-surface-2/70 px-1.5 py-px text-[10.5px] font-medium text-muted">{{ extension }}</span>
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
.he-media-card__frame {
  contain: paint;
  box-shadow: var(--he-shadow-card);
  transition: translate 220ms var(--ease-snappy);
}

/* Scoped content-based styling via :has() without extra template classes. */
.he-media-card:has([role="progressbar"]) .he-card-duration {
  bottom: 12px;
}

.he-media-card:has(.he-badge-missing) .he-media-card__frame {
  box-shadow: 0 0 0 1px rgb(var(--color-danger) / 0.45), var(--he-shadow-card);
}

.he-media-card__backdrop {
  transform: scale(1.12);
  filter: blur(8px) brightness(0.5);
}

.he-media-card__art {
  transition: scale 280ms var(--ease-snappy);
}

@media (hover: hover) {
  .he-media-card:hover .he-media-card__frame {
    box-shadow: var(--he-shadow-card-hover);
    translate: 0 -4px;
  }

  .he-media-card:hover .he-media-card__art {
    scale: 1.045;
  }
}

@media (prefers-reduced-motion: reduce) {
  .he-media-card__frame,
  .he-media-card__art {
    transition: none;
  }
  .he-media-card:hover .he-media-card__frame {
    translate: none;
  }
  .he-media-card:hover .he-media-card__art {
    scale: 1;
  }
}
</style>
