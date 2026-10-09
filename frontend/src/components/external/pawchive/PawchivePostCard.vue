<script setup lang="ts">
import { computed } from 'vue'
import { Film, Image as ImageIcon, Paperclip } from 'lucide-vue-next'
import type { PawchivePost } from '../../../types/pawchive'
import { pawchiveMediaUrl } from '../../../utils/pawchiveApi'
import PawchiveRetryImage from './PawchiveRetryImage.vue'

const props = defineProps<{ post: PawchivePost; selected: boolean }>()
const emit = defineEmits<{ open: []; select: [] }>()
const hasCounts = computed(() => typeof props.post.image_count === 'number' && typeof props.post.video_count === 'number')
const noMedia = computed(() => hasCounts.value && !props.post.image_count && !props.post.video_count)
const mediaLabel = computed(() => {
  if (!hasCounts.value) return `${props.post.reported_attachment_count} 个附件`
  if (noMedia.value) return '没有图片或视频'
  return [props.post.image_count ? `${props.post.image_count} 张图片` : '', props.post.video_count ? `${props.post.video_count} 个视频` : '']
    .filter(Boolean).join('，')
})
const publishedLabel = computed(() => {
  if (!props.post.published_at) return '日期未知'
  const date = new Date(props.post.published_at)
  if (Number.isNaN(date.getTime())) return '日期未知'
  return new Intl.DateTimeFormat('zh-CN', { year: '2-digit', month: '2-digit', day: '2-digit' }).format(date)
})
</script>

<template>
  <article
    class="group flex min-w-0 flex-col overflow-hidden rounded-2xl border bg-surface transition-colors duration-150"
    :class="selected ? 'border-accent/60 bg-accent/8' : 'border-line hover:border-line-strong'"
  >
    <button type="button" class="block w-full min-w-0 text-left focus-ring-inset" :aria-label="`打开作品：${post.title || '无标题作品'}`" @click="emit('open')">
      <div class="relative aspect-[4/3] overflow-hidden bg-surface-2">
        <PawchiveRetryImage :src="pawchiveMediaUrl(post.preview_ref)" alt="" loading="lazy" class="h-full w-full object-cover transition-transform duration-200 ease-out group-hover:scale-[1.03]">
          <template #fallback><div class="flex h-full w-full items-center justify-center"><ImageIcon :size="28" class="text-faint" aria-hidden="true" /></div></template>
        </PawchiveRetryImage>
        <span class="absolute right-2 top-2 inline-flex h-6 items-center gap-2 rounded-md bg-black/60 px-1.5 text-caption font-medium tabular-nums" :class="noMedia ? 'text-white/70' : 'text-white/90'" :title="mediaLabel" :aria-label="mediaLabel">
          <template v-if="!hasCounts"><span class="inline-flex items-center gap-1"><Paperclip :size="12" aria-hidden="true" />{{ post.reported_attachment_count }} 附件</span></template>
          <template v-else-if="noMedia">无媒体</template>
          <template v-else>
            <span v-if="post.image_count" class="inline-flex items-center gap-1"><ImageIcon :size="12" aria-hidden="true" />{{ post.image_count }}</span>
            <span v-if="post.video_count" class="inline-flex items-center gap-1"><Film :size="12" aria-hidden="true" />{{ post.video_count }}</span>
          </template>
        </span>
      </div>
      <h4 class="line-clamp-2 min-h-[2.75em] break-words px-3 pt-2.5 text-body font-medium leading-snug text-ink" :title="post.title || '无标题作品'">{{ post.title || '无标题作品' }}</h4>
    </button>
    <div class="mt-auto flex items-center justify-between gap-1 py-1 pl-3 pr-1">
      <p class="whitespace-nowrap text-caption text-subtle tabular-nums" :title="post.published_at || publishedLabel">{{ publishedLabel }}</p>
      <label class="inline-flex h-9 shrink-0 cursor-pointer items-center gap-1.5 rounded-lg px-2 text-meta font-medium transition-colors focus-within:outline focus-within:outline-2 focus-within:outline-accent hover:bg-surface-2 pointer-coarse:h-11" :class="selected ? 'text-accent-glow' : 'text-muted hover:text-ink'">
        <input type="checkbox" :checked="selected" class="size-4 rounded-sm accent-accent" :aria-label="`选择作品 ${post.title || '无标题作品'} 下载`" @change="emit('select')" />
        <span>{{ selected ? '已选' : '选择' }}</span>
      </label>
    </div>
  </article>
</template>
