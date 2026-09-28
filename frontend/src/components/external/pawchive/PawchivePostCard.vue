<script setup lang="ts">
import { computed, ref } from 'vue'
import { ArrowUpRight, CalendarDays, Image as ImageIcon, Paperclip } from 'lucide-vue-next'
import type { PawchivePost } from '../../../types/pawchive'
import { pawchiveMediaUrl } from '../../../utils/pawchiveApi'

const props = defineProps<{ post: PawchivePost; selected: boolean }>()
const emit = defineEmits<{ open: []; select: [] }>()
const previewFailed = ref(false)
const publishedLabel = computed(() => {
  if (!props.post.published_at) return '日期未知'
  const date = new Date(props.post.published_at)
  if (Number.isNaN(date.getTime())) return '日期未知'
  return new Intl.DateTimeFormat('zh-CN', { year: '2-digit', month: '2-digit', day: '2-digit' }).format(date)
})
</script>

<template>
  <article class="group flex min-w-0 flex-col overflow-hidden rounded-2xl border bg-white/[0.045] shadow-lg shadow-black/10 transition-[border-color,box-shadow,transform] duration-200 hover:border-accent/50 hover:shadow-accent/10 motion-safe:hover:-translate-y-0.5" :class="selected ? 'border-accent/60 ring-1 ring-accent/20' : 'border-white/10'">
    <button type="button" class="block w-full min-w-0 text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-accent" :aria-label="`打开作品：${post.title || '无标题作品'}`" @click="emit('open')">
      <div class="relative aspect-[4/3] overflow-hidden bg-gradient-to-br from-accent/20 via-white/10 to-black/50">
        <img v-if="post.preview_ref && !previewFailed" :src="pawchiveMediaUrl(post.preview_ref)" alt="" loading="lazy" class="h-full w-full object-cover transition-transform duration-300 motion-safe:group-hover:scale-105" @error="previewFailed = true" />
        <div v-else class="flex h-full w-full items-center justify-center"><ImageIcon :size="30" class="text-white/45" aria-hidden="true" /></div>
        <div class="pointer-events-none absolute inset-0 bg-gradient-to-t from-black/30 via-transparent to-black/20" aria-hidden="true"></div>
        <span class="absolute right-2 top-2 inline-flex items-center gap-1 rounded-lg border border-white/20 bg-black/60 px-2 py-1 text-[11px] font-semibold text-white backdrop-blur-sm"><Paperclip :size="12" aria-hidden="true" />{{ post.reported_attachment_count }} 附件</span>
      </div>
      <div class="min-h-[76px] px-3 pb-3 pt-3">
        <div class="flex items-start gap-1">
          <h4 class="line-clamp-2 min-h-10 min-w-0 flex-1 break-words text-sm font-bold leading-5 text-white" :title="post.title || '无标题作品'">{{ post.title || '无标题作品' }}</h4>
          <ArrowUpRight :size="15" class="mt-0.5 shrink-0 text-white/45 transition-colors group-hover:text-accent" aria-hidden="true" />
        </div>
      </div>
    </button>
    <div class="mt-auto flex items-center justify-between gap-1 border-t border-white/10 px-3 py-2">
      <p class="flex min-w-0 items-center gap-1 whitespace-nowrap text-xs text-white/70" :title="post.published_at || publishedLabel"><CalendarDays :size="13" class="hidden shrink-0 text-accent/80 sm:block" aria-hidden="true" />{{ publishedLabel }}</p>
      <label class="inline-flex min-h-11 shrink-0 items-center gap-1 rounded-xl px-1 text-xs font-semibold text-white/85 transition-colors hover:bg-white/10 cursor-pointer focus-within:ring-2 focus-within:ring-accent sm:gap-1.5 sm:px-2">
        <input type="checkbox" :checked="selected" class="h-4 w-4 accent-accent" :aria-label="`选择作品 ${post.title || '无标题作品'} 下载`" @change="emit('select')" />
        <span>{{ selected ? '已选' : '选择' }}</span>
      </label>
    </div>
  </article>
</template>
