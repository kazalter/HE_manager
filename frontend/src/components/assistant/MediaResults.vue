<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Library, Sparkles, Tags, FolderOpen, Copy, ChevronDown } from 'lucide-vue-next'
import MediaCard from '../MediaCard.vue'
import { UiButton } from '../ui'
import { getMediaCards } from '../../utils/assistantApi'
import type { ToolResultDTO } from '../../types/assistant'
import type { Media, Tag } from '../../types'
const props = defineProps<{ results: ToolResultDTO[] }>()
const emit = defineEmits<{ open: [id: number] }>()
interface Item {
  id: number
  title: string
  media_type: string
  tags?: { name: string }[]
  rating?: number
  favorite?: boolean
  view_status?: string
  duration?: number | null
  page_count?: number | null
  file_size?: number | null
  progress?: number
  is_missing?: boolean
}
const PREVIEW_COUNT = 10
const MEDIA_TYPES = ['video', 'manga', 'image', 'audio']
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
// Search totals can exceed the page the model fetched; say so instead of hiding it.
const matched = computed(() =>
  props.results.reduce(
    (sum, c) =>
      c.tool_name === 'search_media' && typeof c.result.total === 'number'
        ? sum + c.result.total
        : sum,
    0,
  ),
)
const basis = computed(() =>
  props.results
    .filter((c) => c.tool_name === 'recommend_media' && typeof c.result.basis === 'string')
    .map((c) => String(c.result.basis)),
)

// Tool results stay path-free for the model; covers are fetched separately for the admin UI.
const cards = ref(new Map<number, Media>())
const pending = ref(new Set<number>())
let request: AbortController | null = null
watch(
  () => media.value.map((m) => m.id).join(','),
  async () => {
    const ids = media.value.map((m) => m.id).filter((id) => !cards.value.has(id)).slice(0, 60)
    if (!ids.length) return
    request?.abort()
    const controller = (request = new AbortController())
    pending.value = new Set(ids)
    try {
      const rows = await getMediaCards(ids, { signal: controller.signal })
      if (controller.signal.aborted || !Array.isArray(rows)) return
      const next = new Map(cards.value)
      for (const row of rows) if (Number.isInteger(row?.id)) next.set(row.id, row)
      cards.value = next
    } catch {
      /* Cards fall back to result metadata with a placeholder cover. */
    } finally {
      if (request === controller) pending.value = new Set()
    }
  },
  { immediate: true },
)
onBeforeUnmount(() => request?.abort())

function fallback(item: Item): Media {
  return {
    id: item.id,
    title: item.title,
    relative_path: '',
    media_type: (MEDIA_TYPES.includes(item.media_type) ? item.media_type : 'image') as Media['media_type'],
    extension: '',
    file_size: item.file_size ?? 0,
    cover_path: null,
    duration: item.duration ?? null,
    width: null,
    height: null,
    page_count: item.page_count ?? null,
    rating: item.rating ?? 0,
    favorite: !!item.favorite,
    view_status: (item.view_status ?? 'unviewed') as Media['view_status'],
    progress: item.progress ?? 0,
    last_opened_at: null,
    source_url: null,
    source_site: null,
    is_missing: !!item.is_missing,
    missing_since: null,
    created_at: '',
    tags: (item.tags ?? []) as Tag[],
  }
}
const expanded = ref(false)
watch(() => props.results, () => { expanded.value = false })
const shown = computed(() =>
  (expanded.value ? media.value : media.value.slice(0, PREVIEW_COUNT)).map((item) => ({
    media: cards.value.get(item.id) || fallback(item),
    loading: pending.value.has(item.id),
  })),
)

const stats = computed(() => props.results.filter((c) => c.tool_name === 'get_library_stats'))
const lists = computed(() =>
  props.results.filter((c) =>
    ['list_tags', 'list_folders', 'list_duplicate_candidates'].includes(c.tool_name),
  ),
)
function list(call: ToolResultDTO): Record<string, unknown>[] {
  return Array.isArray(call.result.items)
    ? (call.result.items as Record<string, unknown>[])
    : []
}
const folderStatus: Record<string, string> = { idle: '空闲', scanning: '扫描中', error: '异常' }
</script>
<template>
  <section
    v-if="media.length || stats.length || lists.length || basis.length"
    aria-label="媒体库查询结果"
    class="min-w-0 space-y-4"
  >
    <div v-if="media.length || basis.length" class="min-w-0 space-y-3 rounded-2xl border border-line bg-surface/70 p-3 sm:p-4">
      <div class="flex min-w-0 flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <h2 class="flex items-center gap-2 text-base font-semibold text-ink">
          <Library :size="17" class="text-accent" aria-hidden="true" />
          找到的作品
          <span v-if="media.length" class="rounded-full bg-accent/15 px-2 py-0.5 text-xs font-medium tabular-nums text-accent-glow">{{ media.length }}</span>
        </h2>
        <p v-if="matched > media.length" class="text-xs text-subtle tabular-nums">
          共匹配 {{ matched }} 部，这里展示管家取回的 {{ media.length }} 部
        </p>
      </div>
      <p
        v-for="(text, i) in basis"
        :key="i"
        class="flex items-start gap-2 rounded-xl bg-surface-2 px-3 py-2 text-sm leading-relaxed text-muted"
      >
        <Sparkles :size="15" class="mt-0.5 shrink-0 text-accent" aria-hidden="true" />
        <span>{{ text }}</span>
      </p>
      <div v-if="media.length" class="assistant-media-grid grid min-w-0 gap-x-3 gap-y-4">
        <div v-for="(card, index) in shown" :key="card.media.id" class="relative min-w-0">
          <MediaCard
            :media="card.media"
            :index="index"
            eager
            shape="poster"
            :title="'打开《' + card.media.title + '》'"
            @click="emit('open', card.media.id)"
          />
          <div
            v-if="card.loading"
            class="skeleton pointer-events-none absolute inset-x-0 top-0 aspect-[2/3] rounded-2xl"
            aria-hidden="true"
          ></div>
        </div>
      </div>
      <UiButton
        v-if="media.length > PREVIEW_COUNT"
        variant="ghost"
        class="min-h-11 w-full"
        :aria-expanded="expanded"
        @click="expanded = !expanded"
      >
        <template #icon><ChevronDown :size="16" class="transition-transform motion-reduce:transition-none" :class="{ 'rotate-180': expanded }" /></template>
        {{ expanded ? '收起' : '显示全部 ' + media.length + ' 部' }}
      </UiButton>
    </div>

    <div
      v-for="call in stats"
      :key="call.tool_call_id"
      class="grid grid-cols-3 gap-2 sm:gap-3"
      role="group"
      aria-label="媒体库统计"
    >
      <div
        v-for="tile in [
          { label: '媒体总数', value: call.result.total },
          { label: '收藏', value: call.result.favorite_count },
          { label: '已看', value: call.result.watched_count },
        ]"
        :key="tile.label"
        class="rounded-2xl border border-line bg-surface/70 px-3 py-3 sm:px-4"
      >
        <p class="text-xs text-muted">{{ tile.label }}</p>
        <p class="mt-1 text-xl font-semibold tabular-nums text-ink sm:text-2xl">{{ tile.value ?? '—' }}</p>
      </div>
    </div>

    <div
      v-for="call in lists"
      :key="call.tool_call_id"
      class="min-w-0 rounded-2xl border border-line bg-surface/70 p-3 text-sm text-muted sm:p-4 [overflow-wrap:anywhere]"
    >
      <template v-if="call.tool_name === 'list_tags'">
        <h3 class="mb-3 flex items-center gap-2 font-medium text-ink"><Tags :size="16" class="text-accent" aria-hidden="true" />标签</h3>
        <ul v-if="list(call).length" class="flex flex-wrap gap-2">
          <li
            v-for="tag in list(call)"
            :key="String(tag.id ?? tag.name)"
            class="inline-flex items-center gap-1.5 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs text-ink"
          >
            {{ tag.name }}<span class="tabular-nums text-subtle">{{ tag.count }}</span>
          </li>
        </ul>
        <p v-else>没有匹配标签</p>
      </template>
      <template v-else-if="call.tool_name === 'list_folders'">
        <h3 class="mb-2 flex items-center gap-2 font-medium text-ink"><FolderOpen :size="16" class="text-accent" aria-hidden="true" />配置目录</h3>
        <ul class="divide-y divide-line">
          <li v-for="folder in list(call)" :key="String(folder.id)" class="flex items-center justify-between gap-3 py-2">
            <span class="min-w-0 text-ink"><span class="text-subtle tabular-nums">#{{ folder.id }}</span> {{ folder.display_name }}</span>
            <span class="shrink-0 text-xs">{{ folderStatus[String(folder.status)] || folder.status }}</span>
          </li>
        </ul>
      </template>
      <template v-else>
        <h3 class="mb-2 flex items-center gap-2 font-medium text-ink"><Copy :size="16" class="text-accent" aria-hidden="true" />重复候选</h3>
        <ul v-if="list(call).length" class="divide-y divide-line">
          <li v-for="candidate in list(call)" :key="String(candidate.id)" class="py-2">
            <p class="text-ink">{{ Array.isArray(candidate.titles) ? candidate.titles.join(' / ') : '' }}</p>
            <p class="mt-0.5 text-xs">{{ candidate.basis }}</p>
          </li>
        </ul>
        <p v-else>没有待处理候选</p>
      </template>
    </div>
    <p
      v-if="results.some((c) => c.result.truncated === true)"
      role="status"
      class="text-sm text-muted"
    >
      部分结果超过展示上限，请缩小查询范围。
    </p>
  </section>
</template>
<style scoped>
.assistant-media-grid {
  grid-template-columns: repeat(auto-fill, minmax(136px, 1fr));
}
@media (min-width: 640px) {
  .assistant-media-grid {
    grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  }
}
</style>
