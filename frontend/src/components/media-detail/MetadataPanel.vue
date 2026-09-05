<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { Plus, Star, Tag as TagIcon, Trash2 } from 'lucide-vue-next'
import { API_BASE_URL } from '../../config'
import type { Media, Tag } from '../../types'

const props = defineProps<{
  media: Media
  coverUrl: string
  mediaTypeLabel: string
  videoProgressPercent: number
  mangaProgressPercent: number
  mangaProgressText: string
  mangaPageTotal: number
}>()

const emit = defineEmits<{
  toggleFavorite: []
  setRating: [score: number]
  addTag: [name: string]
  removeTag: [tagId: number]
}>()

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

onMounted(fetchAllTags)

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
  <aside class="hidden min-[1100px]:flex w-[340px] 2xl:w-[380px] shrink-0 border-l border-white/10 bg-background/95 p-5 flex-col gap-5 overflow-y-auto custom-scrollbar animate-fluid-entrance">
    <div class="flex gap-4">
      <div class="w-24 h-24 rounded-xl bg-white/5 border border-white/10 overflow-hidden shrink-0">
        <img v-if="coverUrl" :src="coverUrl" class="w-full h-full object-cover" :alt="media.title" />
      </div>
      <div class="min-w-0 flex-1">
        <p class="text-xs font-bold text-white/40 uppercase tracking-widest mb-2">媒体信息</p>
        <h3 class="text-xl font-black text-white leading-snug break-words">{{ media.title }}</h3>
        <p class="mt-2 text-xs text-white/40 break-all line-clamp-2">{{ media.relative_path }}</p>
      </div>
    </div>

    <div class="grid grid-cols-2 gap-2 text-sm">
      <div class="rounded-xl bg-white/5 p-3 border border-white/10">
        <p class="text-white/35 text-xs mb-1">类型</p>
        <p class="font-semibold">{{ mediaTypeLabel }}</p>
      </div>
      <div class="rounded-xl bg-white/5 p-3 border border-white/10">
        <p class="text-white/35 text-xs mb-1">进度</p>
        <p class="font-semibold">{{ media.media_type === 'video' ? `${videoProgressPercent}%` : media.media_type === 'manga' ? `${mangaProgressPercent}%` : '-' }}</p>
      </div>
      <div class="rounded-xl bg-white/5 p-3 border border-white/10">
        <p class="text-white/35 text-xs mb-1">时长/页数</p>
        <p class="font-semibold">{{ media.media_type === 'video' ? formatDuration(media.duration) : media.media_type === 'manga' ? mangaProgressText : (media.page_count || '-') }}</p>
      </div>
      <div class="rounded-xl bg-white/5 p-3 border border-white/10">
        <p class="text-white/35 text-xs mb-1">尺寸</p>
        <p class="font-semibold">{{ media.width && media.height ? `${media.width} x ${media.height}` : '-' }}</p>
      </div>
    </div>

    <div v-if="media.media_type === 'video'" class="rounded-xl border border-white/8 bg-white/[0.025] px-3.5 py-3 text-[11px] leading-relaxed text-white/45">
      <p class="font-bold text-white/65 mb-1.5">快捷播放</p>
      <p><kbd class="text-white/75">←</kbd> / <kbd class="text-white/75">→</kbd> 短按跳转 10 秒，长按快退 / 2× 快进</p>
    </div>

    <div v-if="media.media_type === 'manga' && mangaPageTotal" class="rounded-2xl bg-white/5 border border-white/10 p-4">
      <div class="flex items-center justify-between text-sm">
        <span class="font-bold text-white/75">阅读进度</span>
        <span class="font-mono font-bold text-purple-200">{{ mangaProgressText }}</span>
      </div>
      <div class="mt-3 h-1.5 rounded-full bg-white/10 overflow-hidden">
        <div class="h-full bg-purple-300 transition-all duration-300" :style="{ width: `${mangaProgressPercent}%` }"></div>
      </div>
    </div>

    <button
      type="button"
      @click="emit('toggleFavorite')"
      :class="media.favorite ? 'bg-amber-400 text-black shadow-lg shadow-amber-400/20' : 'bg-white/5 text-white/70 hover:text-white hover:bg-white/10'"
      class="w-full h-11 rounded-xl border border-white/10 font-bold flex items-center justify-center gap-2 transition-all cursor-pointer"
    >
      <Star :size="17" :fill="media.favorite ? 'currentColor' : 'none'" />
      {{ media.favorite ? '已收藏' : '收藏' }}
    </button>

    <div>
      <div class="flex items-center justify-between mb-2">
        <p class="text-xs font-bold text-white/40 uppercase tracking-widest">评分</p>
        <span v-if="media.rating" class="text-xs font-bold text-amber-300">{{ media.rating }} 星</span>
      </div>
      <div class="flex gap-2" @mouseleave="hoverScore = 0">
        <button
          v-for="score in 5"
          :key="score"
          type="button"
          @mouseenter="hoverScore = score"
          @click.stop="emit('setRating', score)"
          class="w-10 h-10 rounded-xl bg-white/5 hover:bg-white/10 transition-all text-amber-300 flex items-center justify-center cursor-pointer hover:scale-110 active:scale-95"
          :title="`${score} 星`"
        >
          <Star
            :size="20"
            class="mx-auto transition-transform"
            :fill="(hoverScore > 0 ? hoverScore >= score : media.rating >= score) ? 'currentColor' : 'none'"
          />
        </button>
      </div>
    </div>

    <div>
      <div class="flex items-center gap-2 text-xs font-bold text-white/40 uppercase tracking-widest mb-2">
        <TagIcon :size="14" />
        <span>标签</span>
      </div>
      <div class="flex flex-wrap gap-2 mb-3">
        <span v-for="tag in media.tags" :key="tag.id" class="inline-flex items-center gap-1.5 rounded-lg bg-white/8 border border-white/10 px-2.5 py-1 text-xs">
          <span>{{ tag.name }}</span>
          <button type="button" @click="emit('removeTag', tag.id)" class="text-white/35 hover:text-red-300 cursor-pointer" title="移除标签">
            <Trash2 :size="12" />
          </button>
        </span>
        <span v-if="media.tags.length === 0" class="text-sm text-white/35">还没有标签</span>
      </div>

      <!-- Tag Autocomplete Input Container -->
      <div class="relative">
        <div class="flex gap-2">
          <input
            v-model="tagInput"
            @focus="onTagInputFocus"
            @blur="onTagInputBlur"
            @input="showSuggestions = true"
            @keydown.stop
            @keydown.enter="submitTag()"
            class="min-w-0 flex-1 rounded-xl bg-white/5 border border-white/10 px-3 py-2 text-sm text-white placeholder-white/30 focus:outline-none focus:ring-2 focus:ring-accent/50"
            placeholder="添加标签"
          />
          <button type="button" @click="submitTag()" class="w-10 rounded-xl bg-accent text-white flex items-center justify-center hover:brightness-110 cursor-pointer shrink-0" title="添加标签">
            <Plus :size="18" />
          </button>
        </div>

        <!-- Tag Suggestions Dropdown -->
        <div
          v-if="showSuggestions && tagSuggestions.length > 0"
          class="absolute left-0 right-0 bottom-full mb-1.5 bg-sidebar/95 backdrop-blur-2xl border border-white/15 rounded-xl p-1 shadow-2xl z-50 max-h-48 overflow-y-auto custom-scrollbar"
        >
          <div class="px-2.5 py-1 text-[10px] font-bold text-white/40 uppercase tracking-wider border-b border-white/8">
            匹配已有标签
          </div>
          <button
            v-for="sug in tagSuggestions"
            :key="sug.id"
            type="button"
            @mousedown="submitTag(sug.name)"
            class="w-full px-2.5 py-1.5 text-left text-xs text-white/80 hover:text-white hover:bg-accent/20 rounded-lg flex items-center justify-between transition-colors cursor-pointer"
          >
            <span>{{ sug.name }}</span>
            <span v-if="sug.count" class="text-[10px] text-white/40 font-mono">{{ sug.count }} 项</span>
          </button>
        </div>
      </div>
    </div>
  </aside>
</template>
