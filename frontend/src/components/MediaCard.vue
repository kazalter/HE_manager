<script setup lang="ts">
import { Book, Eye, Film, Headphones, Image as ImageIcon, Play, Star } from 'lucide-vue-next'
import { thumbnailUrl } from '../config'
import mediaPlaceholderUrl from '../assets/media-placeholder.svg?no-inline'
import type { Media } from '../types'

withDefaults(defineProps<{
  media: Media
  index?: number
  eager?: boolean
  virtualized?: boolean
}>(), {
  index: 0,
  eager: false,
  virtualized: false
})

const getThumb = (path: string | null) => path ? thumbnailUrl(path) : mediaPlaceholderUrl

const formatSize = (bytes: number) => {
  if (bytes === 0) return '本地目录'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

const formatDuration = (seconds: number) => {
  const minutes = Math.floor(seconds / 60)
  const rest = seconds % 60
  return `${minutes}:${rest.toString().padStart(2, '0')}`
}

const progressPercent = (media: Media) => {
  if (media.media_type === 'video' && media.duration && media.progress > 0) {
    return Math.min(100, Math.max(0, Math.round((media.progress / media.duration) * 100)))
  }

  if (media.media_type === 'manga' && media.page_count && media.progress >= 0) {
    return Math.min(100, Math.max(0, Math.round(((media.progress + 1) / media.page_count) * 100)))
  }

  return 0
}

const mangaProgressText = (media: Media) => {
  if (media.media_type !== 'manga' || !media.page_count) return ''
  const current = Math.min(media.page_count, Math.max(1, media.progress + 1))
  return `${current} / ${media.page_count}`
}

const formatMeta = (media: Media) => {
  if (media.media_type === 'video') {
    const parts = []
    if (media.duration) parts.push(formatDuration(media.duration))
    const percent = progressPercent(media)
    if (percent > 0) parts.push(`已看 ${percent}%`)
    return parts.length ? parts.join(' · ') : formatSize(media.file_size)
  }
  if (media.media_type === 'manga' && media.page_count) {
    const percent = progressPercent(media)
    return percent > 0 ? `${mangaProgressText(media)} 页 · ${percent}%` : `${media.page_count} 页`
  }
  if (media.width && media.height) return `${media.width} x ${media.height}`
  return formatSize(media.file_size)
}

const typeLabel = (type: Media['media_type']) => {
  if (type === 'video') return '视频'
  if (type === 'manga') return '漫画'
  if (type === 'audio') return '音频'
  return '杂图'
}

const hoverShadowClass = (type: Media['media_type']) => {
  if (type === 'video') return 'group-hover:shadow-[0_20px_40px_-15px_rgba(129,140,248,0.35)]'
  if (type === 'manga') return 'group-hover:shadow-[0_20px_40px_-15px_rgba(192,132,252,0.35)]'
  if (type === 'audio') return 'group-hover:shadow-[0_20px_40px_-15px_rgba(34,211,238,0.35)]'
  return 'group-hover:shadow-[0_20px_40px_-15px_rgba(74,222,128,0.25)]'
}
</script>

<template>
  <button
    :style="{ animationDelay: `${Math.min(24, index) * 35}ms` }"
    :class="{
      'animate-fluid-entrance': !virtualized && index < 16,
      'virtual-card': virtualized,
    }"
    class="lazy-card tap-active group relative text-left flex flex-col cursor-pointer rounded-2xl focus:outline-none focus:ring-2 focus:ring-accent/40"
    style="transition: transform 0.3s cubic-bezier(0.16, 1, 0.3, 1)"
  >
    <div
      class="aspect-[3/4.5] w-full relative overflow-hidden bg-gradient-to-b from-white/5 to-white/[0.01] rounded-2xl border border-white/8 shadow-md group-hover:border-white/20 transition-all duration-300 ease-out"
      :class="hoverShadowClass(media.media_type)"
    >
      <img
        :src="getThumb(media.cover_path)"
        :alt="media.title"
        :loading="eager || virtualized || index < 12 ? 'eager' : 'lazy'"
        decoding="async"
        class="w-full h-full object-cover group-hover:scale-[1.04]"
        style="transition: transform 0.6s cubic-bezier(0.16, 1, 0.3, 1)"
      />

      <!-- Subtle overlay gradient on hover -->
      <div class="absolute inset-0 bg-gradient-to-t from-black/50 via-transparent to-black/5 opacity-70 group-hover:opacity-85 pointer-events-none transition-opacity duration-300"></div>

      <!-- Play / Action Overlay Icon -->
      <div class="absolute inset-0 flex items-center justify-center opacity-0 group-hover:opacity-100 transition-opacity duration-250">
        <div class="w-11 h-11 rounded-full bg-black/60 backdrop-blur-md border border-white/25 shadow-lg flex items-center justify-center scale-90 group-hover:scale-100 hover:scale-105 active:scale-95 transition-transform duration-250">
          <Play v-if="media.media_type === 'video'" :size="18" fill="white" class="ml-0.5 text-white" />
          <Book v-else-if="media.media_type === 'manga'" :size="18" class="text-white" />
          <Headphones v-else-if="media.media_type === 'audio'" :size="18" class="text-white" />
          <ImageIcon v-else :size="18" class="text-white" />
        </div>
      </div>

      <!-- Type Badge -->
      <div class="absolute top-2 right-2 px-1.5 py-0.5 rounded-md bg-black/75 border border-white/10 flex items-center gap-1 z-20">
        <Film v-if="media.media_type === 'video'" :size="9" class="text-accent" />
        <Book v-else-if="media.media_type === 'manga'" :size="9" class="text-purple-300" />
        <Headphones v-else-if="media.media_type === 'audio'" :size="9" class="text-cyan-300" />
        <ImageIcon v-else :size="9" class="text-green-300" />
        <span class="text-[9px] font-black text-white/90 uppercase tracking-wider">{{ typeLabel(media.media_type) }}</span>
      </div>

      <!-- Favorite Badge -->
      <div v-if="media.favorite" class="absolute top-2 left-2 w-6 h-6 rounded-md bg-black/75 border border-white/10 flex items-center justify-center text-amber-300 z-20">
        <Star :size="11" fill="currentColor" />
      </div>

      <!-- Progress Badge (Manga) -->
      <div v-if="media.media_type === 'manga' && media.page_count && progressPercent(media) > 0" class="absolute left-2 bottom-3 rounded-md bg-black/75 border border-white/10 px-1.5 py-0.5 z-20">
        <span class="text-[9px] font-black text-white/90">{{ mangaProgressText(media) }}</span>
      </div>

      <!-- Progress Bar -->
      <div v-if="progressPercent(media) > 0" class="absolute inset-x-0 bottom-0 h-1 bg-black/40">
        <div
          class="h-full rounded-full transition-all duration-300"
          :class="media.media_type === 'manga' ? 'bg-purple-400' : 'bg-accent'"
          :style="{ width: `${progressPercent(media)}%` }"
        ></div>
      </div>

      <!-- Missing File Overlay -->
      <div v-if="media.is_missing" class="absolute inset-x-2 bottom-2 rounded-md bg-red-500/90 border border-red-400/20 px-1.5 py-1 text-center text-[10px] font-black text-white z-20 shadow-md">
        文件丢失
      </div>
    </div>

    <!-- Title and Meta -->
    <div class="mt-2.5 px-0.5 tracking-tight min-w-0 w-full">
      <h3 class="text-xs font-bold text-white/85 group-hover:text-accent line-clamp-1 leading-snug mb-1 transition-colors duration-300" :title="media.title">
        {{ media.title }}
      </h3>
      <div class="flex items-center gap-1.5 text-[10px] text-white/40 font-semibold tracking-wide min-w-0">
        <span class="px-1 py-0.2 rounded bg-white/5 border border-white/8 font-bold text-white/50 shrink-0 text-[8px] uppercase">{{ media.extension.replace('.', '') || 'DIR' }}</span>
        <span class="truncate">{{ formatMeta(media) }}</span>
        <span v-if="media.view_status === 'viewed'" class="ml-auto text-green-400 shrink-0" title="已看">
          <Eye :size="11" />
        </span>
      </div>
    </div>
  </button>
</template>
