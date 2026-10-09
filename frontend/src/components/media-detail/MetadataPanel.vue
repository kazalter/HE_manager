<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { Plus, Star, X } from 'lucide-vue-next'
import { API_BASE_URL } from '../../config'
import type { Media, Tag } from '../../types'
import { buttonClass, controlClass, iconButtonClass, menuItemClass, popoverClass } from '../ui'

const props = defineProps<{
  media: Media
  /** Render in page flow (phone video detail) instead of as a sidebar / bottom sheet. */
  inline?: boolean
  coverUrl: string
  mediaTypeLabel: string
  videoProgressPercent: number
  mangaProgressPercent: number
  mangaProgressText: string
  mangaPageTotal: number
}>()

const emit = defineEmits<{
  close: []
  toggleFavorite: []
  setRating: [score: number]
  addTag: [name: string]
  removeTag: [tagId: number]
}>()

const closeRef = ref<HTMLButtonElement | null>(null)
const tagInput = ref('')
const hoverScore = ref(0)
const allKnownTags = ref<Tag[]>([])
const showSuggestions = ref(false)

const fetchAllTags = async () => {
  try {
    const res = await axios.get(`${API_BASE_URL}/tags`)
    allKnownTags.value = res.data || []
  } catch {
    // non-fatal
  }
}

onMounted(() => { void fetchAllTags(); if (window.innerWidth < 900) closeRef.value?.focus() })

const tagSuggestions = computed(() => {
  const query = tagInput.value.trim().toLowerCase()
  if (!query) return []
  const currentTagNames = new Set(props.media.tags.map(t => t.name.toLowerCase()))
  return allKnownTags.value
    .filter(t => t.name.toLowerCase().includes(query) && !currentTagNames.has(t.name.toLowerCase()))
    .slice(0, 8)
})

const formatDuration = (seconds: number | null) => {
  if (!seconds) return '未知'
  const hours = Math.floor(seconds / 3600)
  const minutes = Math.floor((seconds % 3600) / 60)
  const rest = seconds % 60
  return hours > 0
    ? `${hours}:${minutes.toString().padStart(2, '0')}:${rest.toString().padStart(2, '0')}`
    : `${minutes}:${rest.toString().padStart(2, '0')}`
}

const formatSize = (bytes: number) => {
  if (!bytes) return '本地目录'
  const k = 1024
  const sizes = ['B', 'KB', 'MB', 'GB', 'TB']
  const i = Math.floor(Math.log(bytes) / Math.log(k))
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`
}

const progressPercent = computed(() =>
  props.media.media_type === 'video' ? props.videoProgressPercent : props.media.media_type === 'manga' ? props.mangaProgressPercent : 0)
const showProgress = computed(() =>
  (props.media.media_type === 'video' && !!props.media.duration) || (props.media.media_type === 'manga' && props.mangaPageTotal > 0))
const progressLabel = computed(() => props.media.media_type === 'manga' ? '阅读进度' : '观看进度')
const progressValue = computed(() => props.media.media_type === 'manga'
  ? `${props.mangaProgressText} 页`
  : `${formatDuration(props.media.progress || 0)} / ${formatDuration(props.media.duration)}`)

const details = computed(() => {
  const media = props.media
  const rows: { label: string; value: string }[] = [{ label: '类型', value: props.mediaTypeLabel }]
  if (media.media_type === 'video' || media.media_type === 'audio') rows.push({ label: '时长', value: formatDuration(media.duration) })
  else if (media.media_type === 'manga') rows.push({ label: '页数', value: props.mangaPageTotal ? `${props.mangaPageTotal} 页` : media.page_count ? `${media.page_count} 页` : '-' })
  if (media.width && media.height) rows.push({ label: '尺寸', value: `${media.width}×${media.height}` })
  rows.push({ label: '格式', value: media.extension.replace('.', '').toUpperCase() || '目录' })
  rows.push({ label: '大小', value: formatSize(media.file_size) })
  return rows
})

const submitTag = (suggestedName?: string) => {
  const name = (suggestedName ?? tagInput.value).trim()
  if (!name) return
  emit('addTag', name)
  tagInput.value = ''
  showSuggestions.value = false
}

const onTagInputFocus = () => {
  if (tagInput.value.trim()) showSuggestions.value = true
}

const onTagInputBlur = () => {
  setTimeout(() => {
    showSuggestions.value = false
  }, 250)
}
</script>

<template>
  <aside
    :class="inline
      ? 'he-metadata-inline flex w-full flex-col gap-6 bg-background px-4 pt-5'
      : 'he-metadata-panel custom-scrollbar hidden w-[360px] shrink-0 flex-col gap-6 overflow-y-auto border-l border-line bg-surface p-5 min-[1100px]:flex 2xl:w-[400px] 2xl:p-6'"
    :aria-label="inline ? '媒体信息' : undefined"
  >
    <div v-if="!inline" class="flex items-center justify-between min-[900px]:hidden">
      <h2 class="text-heading font-semibold text-ink">媒体信息</h2>
      <button ref="closeRef" type="button" :class="iconButtonClass('ghost', 'lg')" aria-label="关闭媒体信息" title="关闭媒体信息" @click="emit('close')">
        <X :size="20" aria-hidden="true" />
      </button>
    </div>

    <header class="flex gap-4">
      <div v-if="coverUrl && !inline" class="relative size-20 shrink-0 overflow-hidden rounded-lg bg-surface-2">
        <img :src="coverUrl" class="h-full w-full object-cover" :alt="media.title" />
        <div class="pointer-events-none absolute inset-0 rounded-lg ring-1 ring-inset ring-white/8"></div>
      </div>
      <div class="min-w-0 flex-1">
        <h3 class="line-clamp-3 break-words text-heading font-semibold leading-snug text-ink" :title="media.title">{{ media.title }}</h3>
        <p class="mt-1.5 line-clamp-2 break-all font-mono text-caption text-subtle" :title="media.relative_path">{{ media.relative_path }}</p>
      </div>
    </header>

    <div class="flex items-center gap-3">
      <div class="-ml-1.5 flex items-center pointer-coarse:-ml-2.5" role="group" aria-label="评分" @mouseleave="hoverScore = 0">
        <button
          v-for="score in 5"
          :key="score"
          type="button"
          class="grid size-8 place-items-center rounded-lg text-star transition-colors duration-150 hover:bg-surface-2 focus-ring pointer-coarse:size-10"
          :title="`${score} 星`"
          :aria-label="`评为 ${score} 星`"
          @mouseenter="hoverScore = score"
          @click.stop="emit('setRating', score)"
        >
          <Star
            :size="18"
            :class="(hoverScore > 0 ? hoverScore >= score : media.rating >= score) ? '' : 'text-faint'"
            :fill="(hoverScore > 0 ? hoverScore >= score : media.rating >= score) ? 'currentColor' : 'none'"
            aria-hidden="true"
          />
        </button>
      </div>
      <span class="whitespace-nowrap text-meta text-subtle tabular-nums">{{ media.rating ? `${media.rating} 星` : '未评分' }}</span>
      <button
        type="button"
        class="ml-auto"
        :class="[buttonClass('secondary', inline ? 'lg' : 'md'), media.favorite ? '!border-star/30 !bg-star/12 !text-star' : '']"
        :aria-pressed="media.favorite"
        @click="emit('toggleFavorite')"
      >
        <Star :size="16" :fill="media.favorite ? 'currentColor' : 'none'" aria-hidden="true" />
        {{ media.favorite ? '已收藏' : '收藏' }}
      </button>
    </div>

    <section v-if="showProgress">
      <div class="flex items-baseline justify-between gap-3">
        <span class="text-meta font-medium text-muted">{{ progressLabel }}</span>
        <span class="text-meta text-subtle tabular-nums">{{ progressValue }} · {{ progressPercent }}%</span>
      </div>
      <div class="mt-2 h-1 overflow-hidden rounded-sm bg-surface-3" role="progressbar" :aria-label="progressLabel" :aria-valuenow="progressPercent" aria-valuemin="0" aria-valuemax="100">
        <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: `${progressPercent}%` }"></div>
      </div>
    </section>

    <section>
      <h4 class="mb-1 text-meta font-medium text-muted">文件信息</h4>
      <dl class="divide-y divide-line">
        <div v-for="row in details" :key="row.label" class="flex items-center justify-between gap-4 py-2 text-meta">
          <dt class="shrink-0 text-subtle">{{ row.label }}</dt>
          <dd class="truncate text-right text-ink tabular-nums">{{ row.value }}</dd>
        </div>
      </dl>
    </section>

    <section>
      <h4 class="mb-2.5 text-meta font-medium text-muted">标签</h4>
      <div class="mb-3 flex flex-wrap gap-1.5">
        <span v-for="tag in media.tags" :key="tag.id" class="inline-flex h-7 items-center gap-1 rounded-full border border-line bg-surface-2 pl-2.5 pr-1 text-caption font-medium text-muted">
          <span class="truncate">{{ tag.name }}</span>
          <button
            type="button"
            class="grid size-5 place-items-center rounded-full text-subtle transition-colors hover:bg-danger/12 hover:text-danger focus-ring pointer-coarse:size-8"
            title="移除标签"
            :aria-label="`移除标签 ${tag.name}`"
            @click="emit('removeTag', tag.id)"
          >
            <X :size="12" aria-hidden="true" />
          </button>
        </span>
        <span v-if="media.tags.length === 0" class="text-meta text-subtle">还没有标签</span>
      </div>

      <div class="relative">
        <div class="flex gap-2">
          <input
            v-model="tagInput"
            :class="controlClass(inline ? 'lg' : 'md')"
            placeholder="添加标签"
            aria-label="添加标签"
            @focus="onTagInputFocus"
            @blur="onTagInputBlur"
            @input="showSuggestions = true"
            @keydown.stop
            @keydown.enter="submitTag()"
          />
          <button type="button" :class="iconButtonClass('secondary', inline ? 'lg' : 'md')" title="添加标签" aria-label="添加标签" @click="submitTag()">
            <Plus :size="18" aria-hidden="true" />
          </button>
        </div>

        <div
          v-if="showSuggestions && tagSuggestions.length > 0"
          :class="popoverClass"
          class="custom-scrollbar absolute bottom-full left-0 right-0 z-50 mb-1.5 max-h-56 overflow-y-auto"
        >
          <p class="px-2.5 pb-1 pt-0.5 text-caption text-subtle">匹配已有标签</p>
          <button
            v-for="sug in tagSuggestions"
            :key="sug.id"
            type="button"
            :class="menuItemClass"
            @mousedown="submitTag(sug.name)"
          >
            <span class="truncate">{{ sug.name }}</span>
            <span v-if="sug.count" class="ml-auto shrink-0 text-caption text-subtle tabular-nums">{{ sug.count }} 项</span>
          </button>
        </div>
      </div>
    </section>

    <section v-if="media.media_type === 'video' && !inline" class="rounded-lg bg-surface-2 p-3 text-caption leading-relaxed text-subtle pointer-coarse:hidden">
      <p class="mb-1 font-medium text-muted">快捷播放</p>
      <p>
        <kbd class="he-kbd">←</kbd> / <kbd class="he-kbd">→</kbd>
        短按跳转 10 秒，长按快退 / 2× 快进
      </p>
    </section>
  </aside>
</template>

<style scoped>
.he-kbd {
  display: inline-flex;
  height: 20px;
  min-width: 20px;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  border: 1px solid rgb(var(--color-line-strong));
  background: rgb(var(--color-surface-3));
  padding-inline: 4px;
  color: rgb(var(--color-muted));
}

.he-metadata-inline {
  padding-bottom: calc(24px + env(safe-area-inset-bottom));
}

@media (max-width: 899px) {
  .he-metadata-panel {
    display: flex;
    position: absolute;
    z-index: 60;
    inset: auto 0 0;
    width: 100%;
    max-height: 75dvh;
    border-left: 0;
    border-top: 1px solid rgb(var(--color-line-strong));
    border-radius: 20px 20px 0 0;
    background: rgb(var(--color-surface-3));
    box-shadow: var(--shadow-modal);
    padding: 16px 16px calc(24px + env(safe-area-inset-bottom));
  }
}
</style>
