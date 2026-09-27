<script setup lang="ts">
import { Film, Heart, Image as ImageIcon, Loader2, UserRound } from 'lucide-vue-next'
import type { PawchivePost } from '../../../types/pawchive'
import { pawchiveMediaUrl } from '../../../utils/pawchiveApi'

defineProps<{ post: PawchivePost; selected: boolean; favorite: boolean; canFavorite: boolean; favoriteBusy: boolean }>()
const emit = defineEmits<{ open: []; creator: []; select: []; favorite: [] }>()
</script>

<template>
  <article class="rounded-2xl border border-white/10 bg-white/[0.04] overflow-hidden hover:border-accent/45 transition-colors">
    <button type="button" class="block w-full text-left cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" :aria-label="`打开帖子：${post.title}`" @click="emit('open')">
      <div class="aspect-[4/3] bg-black/30 flex items-center justify-center overflow-hidden">
        <img v-if="post.preview_ref" :src="pawchiveMediaUrl(post.preview_ref)" alt="" loading="lazy" class="w-full h-full object-cover" />
        <ImageIcon v-else :size="32" class="text-white/25" aria-hidden="true" />
      </div>
      <div class="p-4 space-y-2">
        <h3 class="text-sm font-bold text-white line-clamp-2 min-h-10">{{ post.title }}</h3>
        <p class="text-xs text-white/45">{{ post.published_at ? new Date(post.published_at).toLocaleString() : '发布时间未知' }}</p>
        <p class="flex items-center gap-1.5 text-xs text-white/65"><Film :size="13" aria-hidden="true" />附件 {{ post.reported_attachment_count }} · 可播放数打开后确定</p>
      </div>
    </button>
    <div class="px-4 pb-4 flex items-center justify-between gap-2">
      <button type="button" class="min-h-11 max-w-full flex items-center gap-1.5 text-xs font-semibold text-accent hover:text-white cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent rounded-lg" :aria-label="`查看创作者 ${post.creator_name} 的帖子`" @click="emit('creator')">
        <UserRound :size="14" aria-hidden="true" /><span class="truncate">{{ post.creator_name }}</span>
      </button>
      <button
        type="button"
        :disabled="!canFavorite || favoriteBusy"
        :aria-label="favorite ? `取消收藏作者 ${post.creator_name}` : `收藏作者 ${post.creator_name}`"
        :aria-pressed="favorite"
        :title="canFavorite ? (favorite ? '取消收藏作者' : '收藏作者') : '登录 Pawchive 账号后可收藏作者'"
        class="min-h-11 shrink-0 inline-flex items-center gap-1.5 rounded-lg px-2 text-xs text-white/70 hover:text-pink-200 disabled:opacity-45 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        @click="emit('favorite')"
      >
        <Loader2 v-if="favoriteBusy" :size="14" class="animate-spin" aria-hidden="true" />
        <Heart v-else :size="14" :fill="favorite ? 'currentColor' : 'none'" aria-hidden="true" />
        {{ favoriteBusy ? '处理中…' : favorite ? '已收藏' : '收藏作者' }}
      </button>
      <label class="min-h-11 shrink-0 flex items-center gap-2 text-xs text-white/75 cursor-pointer"><input type="checkbox" :checked="selected" class="accent-current w-5 h-5" :aria-label="`选择帖子 ${post.title} 下载`" @change="emit('select')" />选择</label>
    </div>
  </article>
</template>
