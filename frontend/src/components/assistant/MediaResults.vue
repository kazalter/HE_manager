<script setup lang="ts">
import { computed } from 'vue'
import { UiButton, UiCard } from '../ui'
import type { ToolResultDTO } from '../../types/assistant'
const props = defineProps<{ results: ToolResultDTO[] }>()
const emit = defineEmits<{ open: [id: number] }>()
interface Item {
  id: number
  title: string
  media_type: string
  tags?: { name: string }[]
  rating?: number
}
const media = computed(() => {
  const found = new Map<number, Item>()
  for (const call of props.results) {
    const candidates =
      call.tool_name === 'get_media_detail'
        ? [call.result]
        : ['search_media', 'recommend_media'].includes(call.tool_name) &&
            Array.isArray(call.result.items)
          ? call.result.items
          : []
    for (const value of candidates) {
      const item = value as Item
      if (
        Number.isInteger(item?.id) &&
        item.id > 0 &&
        typeof item.title === 'string'
      )
        found.set(item.id, item)
    }
  }
  return [...found.values()]
})
const labels: Record<string, string> = {
  manga: '漫画',
  video: '视频',
  image: '图片',
  audio: '音频',
}
const info = computed(() =>
  props.results.filter((c) =>
    [
      'get_library_stats',
      'list_tags',
      'list_folders',
      'list_duplicate_candidates',
      'recommend_media',
    ].includes(c.tool_name),
  ),
)
function list(call: ToolResultDTO): Record<string, unknown>[] {
  return Array.isArray(call.result.items)
    ? (call.result.items as Record<string, unknown>[])
    : []
}
</script>
<template>
  <section
    v-if="media.length || info.length"
    aria-label="媒体库查询结果"
    class="min-w-0 space-y-3"
  >
    <h2 class="text-base font-semibold text-ink">查询结果</h2>
    <div class="grid min-w-0 gap-3 sm:grid-cols-2">
      <UiCard v-for="item in media" :key="item.id" padding="sm" class="min-w-0">
        <p class="text-sm text-muted">
          {{ labels[item.media_type] || '媒体'
          }}<span v-if="item.rating"> · {{ item.rating }} 星</span>
        </p>
        <h3 class="my-2 font-medium text-ink [overflow-wrap:anywhere]">
          {{ item.title }}
        </h3>
        <p
          v-if="item.tags?.length"
          class="mb-3 text-sm text-muted [overflow-wrap:anywhere]"
        >
          {{ item.tags.map((t) => t.name).join(' · ') }}
        </p>
        <UiButton class="min-h-11" size="sm" @click="emit('open', item.id)"
          >打开媒体</UiButton
        >
      </UiCard>
    </div>
    <UiCard
      v-for="call in info"
      :key="call.tool_call_id"
      padding="sm"
      class="min-w-0 text-sm text-muted [overflow-wrap:anywhere]"
    >
      <template v-if="call.tool_name === 'get_library_stats'"
        >媒体 {{ call.result.total }} 项 · 收藏
        {{ call.result.favorite_count }} 项 · 已看
        {{ call.result.watched_count }} 项</template
      >
      <template v-else-if="call.tool_name === 'recommend_media'"
        >推荐依据：{{ call.result.basis }}</template
      >
      <template v-else-if="call.tool_name === 'list_tags'"
        ><h3 class="mb-2 font-medium text-ink">标签</h3>
        <p>
          {{
            list(call)
              .map((t) => String(t.name) + ' (' + String(t.count) + ')')
              .join(' · ') || '没有匹配标签'
          }}
        </p></template
      >
      <template v-else-if="call.tool_name === 'list_folders'"
        ><h3 class="mb-2 font-medium text-ink">配置目录</h3>
        <p v-for="folder in list(call)" :key="String(folder.id)">
          #{{ folder.id }} · {{ folder.display_name }} · {{ folder.status }}
        </p></template
      >
      <template v-else
        ><h3 class="mb-2 font-medium text-ink">重复候选</h3>
        <p v-for="candidate in list(call)" :key="String(candidate.id)">
          {{
            Array.isArray(candidate.titles) ? candidate.titles.join(' / ') : ''
          }}
          · {{ candidate.basis }}
        </p>
        <p v-if="!list(call).length">没有待处理候选</p></template
      >
    </UiCard>
    <p
      v-if="results.some((c) => c.result.truncated === true)"
      role="status"
      class="text-sm text-muted"
    >
      部分结果超过展示上限，请缩小查询范围。
    </p>
  </section>
</template>
