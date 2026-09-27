<script setup lang="ts">
import { Heart, Loader2, UserRound } from 'lucide-vue-next'
import type { PawchiveCreatorCandidate } from '../../../types/pawchive'
import { pawchiveMediaUrl } from '../../../utils/pawchiveApi'

defineProps<{
  creator: PawchiveCreatorCandidate
  favorite: boolean
  busy: boolean
  canFavorite: boolean
}>()
const emit = defineEmits<{ open: []; favorite: [] }>()
</script>

<template>
  <article class="rounded-2xl border border-white/10 bg-white/[0.04] overflow-hidden hover:border-accent/45 transition-colors">
    <div class="aspect-[4/3] bg-black/30 flex items-center justify-center overflow-hidden">
      <img v-if="creator.latest_post.preview_ref" :src="pawchiveMediaUrl(creator.latest_post.preview_ref)" alt="" loading="lazy" class="w-full h-full object-cover" />
      <UserRound v-else :size="32" class="text-white/25" aria-hidden="true" />
    </div>
    <div class="p-4 space-y-2">
      <h3 class="text-sm font-bold text-white truncate">{{ creator.creator_name }}</h3>
      <p class="text-xs text-white/45">{{ creator.service }} · {{ creator.post_count }} 篇匹配帖子</p>
      <p class="text-xs text-white/60 line-clamp-2">{{ creator.latest_post.title }}</p>
    </div>
    <div class="px-4 pb-4 flex items-center justify-between gap-2">
      <button type="button" class="min-h-11 inline-flex items-center gap-1.5 rounded-lg text-xs font-semibold text-accent hover:text-white focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent" @click="emit('open')">
        <UserRound :size="14" aria-hidden="true" />查看作者帖子
      </button>
      <button
        type="button"
        :disabled="!canFavorite || busy"
        :aria-label="favorite ? `取消收藏作者 ${creator.creator_name}` : `收藏作者 ${creator.creator_name}`"
        :aria-pressed="favorite"
        :title="canFavorite ? (favorite ? '取消收藏作者' : '收藏作者') : '登录 Pawchive 账号后可收藏作者'"
        class="min-h-11 shrink-0 inline-flex items-center gap-1.5 rounded-lg px-2 text-xs text-white/70 hover:text-pink-200 disabled:opacity-45 disabled:cursor-not-allowed focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-accent"
        @click="emit('favorite')"
      >
        <Loader2 v-if="busy" :size="14" class="animate-spin" aria-hidden="true" />
        <Heart v-else :size="14" :fill="favorite ? 'currentColor' : 'none'" aria-hidden="true" />
        {{ busy ? '处理中…' : favorite ? '已收藏' : '收藏作者' }}
      </button>
    </div>
  </article>
</template>
