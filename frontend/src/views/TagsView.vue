<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import axios from 'axios'
import { Tags as TagsIcon, RefreshCw, Pencil, GitMerge, Trash2, Check, X, Search, ChevronDown, AlertTriangle } from 'lucide-vue-next'
import { API_BASE_URL } from '../config'
import type { Tag } from '../types'
import ThemeSelect from '../components/ThemeSelect.vue'
import { EmptyState, PageHeader, SectionHeader, UiButton, UiCard, UiIconButton, UiInput, UiSkeleton, controlClass } from '../components/ui'

const NAMESPACES = [
  { value: 'general', label: '通用' },
  { value: 'artist', label: '作者' },
  { value: 'character', label: '角色' },
  { value: 'parody', label: '出处' },
  { value: 'source', label: '来源' },
]
const NS_ORDER = NAMESPACES.map(n => n.value)
const nsLabel = (ns: string) => NAMESPACES.find(n => n.value === ns)?.label ?? ns

const tags = ref<Tag[]>([])
const loading = ref(true)
const errorMessage = ref('')
const refreshSpinning = ref(false)
const search = ref('')
const collapsed = ref<Set<string>>(new Set())

const zeroCountTags = computed(() => tags.value.filter(t => (t.count ?? 0) === 0))

// edit / merge state
const editId = ref<number | null>(null)
const editName = ref('')
const editNs = ref('general')
const rowError = ref<{ id: number; msg: string } | null>(null)
const mergeId = ref<number | null>(null)
const mergeSearch = ref('')
// 0 = "no target chosen" sentinel (no tag has id 0; stays falsy for the
// existing !mergeTargetId guards) so the value fits ThemeSelect's typed model.
const mergeTargetId = ref<number>(0)
const busy = ref(false)

const fetchTags = async () => {
  loading.value = tags.value.length === 0
  errorMessage.value = ''
  try {
    const res = await axios.get<Tag[]>(`${API_BASE_URL}/tags`)
    tags.value = res.data
  } catch (err: any) {
    errorMessage.value = err?.response?.data?.detail || '加载标签失败，请确认后端服务正在运行。'
  } finally {
    loading.value = false
  }
}

const refresh = async () => {
  if (refreshSpinning.value) return
  refreshSpinning.value = true
  await fetchTags()
  setTimeout(() => (refreshSpinning.value = false), 400)
}

onMounted(fetchTags)

const grouped = computed(() => {
  const q = search.value.trim().toLowerCase()
  const groups: Record<string, Tag[]> = {}
  for (const t of tags.value) {
    if (q && !t.name.toLowerCase().includes(q)) continue
    const ns = t.namespace || 'general'
    ;(groups[ns] ??= []).push(t)
  }
  const known = NS_ORDER.filter(n => groups[n])
  const extra = Object.keys(groups).filter(n => !NS_ORDER.includes(n)).sort()
  return [...known, ...extra].map(ns => ({
    ns,
    label: nsLabel(ns),
    items: groups[ns].sort((a, b) => a.name.localeCompare(b.name)),
  }))
})

const totalShown = computed(() => grouped.value.reduce((s, g) => s + g.items.length, 0))

const toggleGroup = (ns: string) => {
  const s = new Set(collapsed.value)
  s.has(ns) ? s.delete(ns) : s.add(ns)
  collapsed.value = s
}

const startEdit = (t: Tag) => {
  editId.value = t.id
  editName.value = t.name
  editNs.value = t.namespace
  rowError.value = null
  mergeId.value = null
}
const cancelEdit = () => {
  editId.value = null
  rowError.value = null
}
const saveEdit = async (t: Tag) => {
  const name = editName.value.trim()
  if (!name || busy.value) return
  busy.value = true
  rowError.value = null
  try {
    await axios.patch(`${API_BASE_URL}/tags/${t.id}`, { name, namespace: editNs.value })
    editId.value = null
    await fetchTags()
  } catch (err: any) {
    rowError.value = { id: t.id, msg: err?.response?.data?.detail || '重命名失败' }
  } finally {
    busy.value = false
  }
}

const startMerge = (t: Tag) => {
  mergeId.value = t.id
  mergeTargetId.value = 0
  mergeSearch.value = ''
  rowError.value = null
  editId.value = null
}
const mergeCandidates = computed(() => {
  const q = mergeSearch.value.trim().toLowerCase()
  return tags.value
    .filter(t => t.id !== mergeId.value && (!q || t.name.toLowerCase().includes(q) || nsLabel(t.namespace).toLowerCase().includes(q)))
    .sort((a, b) => (a.namespace + a.name).localeCompare(b.namespace + b.name))
})
const mergeOptions = computed(() => [
  { value: 0, label: '选择目标标签…' },
  ...mergeCandidates.value.map(c => ({
    value: c.id,
    label: `${nsLabel(c.namespace)}:${c.name} (${c.count ?? 0})`,
  })),
])
const confirmMerge = async (t: Tag) => {
  if (!mergeTargetId.value || busy.value) return
  const target = tags.value.find(x => x.id === mergeTargetId.value)
  if (!target) return
  if (!confirm(`把「${nsLabel(t.namespace)}:${t.name}」(${t.count ?? 0}) 合并进「${nsLabel(target.namespace)}:${target.name}」？此标签将被删除。`)) return
  busy.value = true
  rowError.value = null
  try {
    await axios.post(`${API_BASE_URL}/tags/${t.id}/merge`, { target_id: mergeTargetId.value })
    mergeId.value = null
    await fetchTags()
  } catch (err: any) {
    rowError.value = { id: t.id, msg: err?.response?.data?.detail || '合并失败' }
  } finally {
    busy.value = false
  }
}

const cleanupZeroCountTags = async () => {
  const targets = zeroCountTags.value
  if (targets.length === 0 || busy.value) return
  if (!confirm(`确认一键清理全部 ${targets.length} 个引用为 0 的孤立标签？`)) return
  busy.value = true
  errorMessage.value = ''
  try {
    for (const t of targets) {
      await axios.delete(`${API_BASE_URL}/tags/${t.id}`)
    }
    await fetchTags()
  } catch (err: any) {
    errorMessage.value = err?.response?.data?.detail || '清理标签失败'
  } finally {
    busy.value = false
  }
}

const removeTag = async (t: Tag) => {
  if (busy.value) return
  if (!confirm(`删除标签「${nsLabel(t.namespace)}:${t.name}」？将从 ${t.count ?? 0} 个媒体上移除（媒体本身不受影响）。`)) return
  busy.value = true
  try {
    await axios.delete(`${API_BASE_URL}/tags/${t.id}`)
    await fetchTags()
  } catch (err: any) {
    rowError.value = { id: t.id, msg: err?.response?.data?.detail || '删除失败' }
  } finally {
    busy.value = false
  }
}
</script>

<template>
  <div class="min-h-full">
    <PageHeader title="标签管理" :count="`${tags.length} 个`" description="重命名、合并、清理标签">
      <template #actions>
        <UiButton
          v-if="zeroCountTags.length > 0"
          variant="secondary"
          class="pointer-coarse:h-11"
          :disabled="busy"
          :title="`一键清理 ${zeroCountTags.length} 个 0 引用标签`"
          @click="cleanupZeroCountTags"
        >
          <template #icon><Trash2 :size="16" class="text-warning" /></template>
          清理 {{ zeroCountTags.length }} 个孤立标签
        </UiButton>
        <UiIconButton label="刷新" variant="secondary" @click="refresh">
          <RefreshCw :size="18" :class="{ 'animate-spin': refreshSpinning }" />
        </UiIconButton>
      </template>
      <UiInput v-model="search" type="search" placeholder="搜索标签名…" aria-label="搜索标签名" class="w-full sm:w-80">
        <template #leading><Search :size="16" /></template>
        <template #trailing><UiIconButton v-if="search" label="清除搜索" size="sm" @click="search = ''"><X :size="14" /></UiIconButton></template>
      </UiInput>
    </PageHeader>

    <div class="page-gutter pb-12">
      <div class="page-container">
        <div v-if="loading" class="space-y-10" aria-busy="true">
          <section v-for="n in 2" :key="n">
            <UiSkeleton shape="text" class="mb-3 w-24" />
            <UiCard padding="sm" class="grid grid-cols-1 gap-x-6 gap-y-3 md:grid-cols-2 xl:grid-cols-3">
              <UiSkeleton v-for="m in 9" :key="m" class="h-9 w-full rounded-lg" />
            </UiCard>
          </section>
        </div>

        <UiCard v-else-if="errorMessage" padding="none">
          <EmptyState tone="danger" :icon="AlertTriangle" title="加载标签失败" :description="errorMessage">
            <UiButton variant="secondary" size="sm" @click="refresh"><template #icon><RefreshCw :size="14" /></template>重试</UiButton>
          </EmptyState>
        </UiCard>

        <EmptyState
          v-else-if="totalShown === 0"
          :icon="search ? Search : TagsIcon"
          :title="search ? '没有匹配的标签' : '还没有标签'"
          :description="search ? '换个关键词试试。' : '在媒体详情里添加标签后，会在这里集中管理。'"
        >
          <UiButton v-if="search" variant="secondary" size="sm" @click="search = ''">清除搜索</UiButton>
        </EmptyState>

        <div v-else class="space-y-10">
          <section v-for="group in grouped" :key="group.ns">
            <SectionHeader :title="group.label" :count="group.items.length">
              <template #actions>
                <UiButton variant="ghost" size="sm" :aria-expanded="!collapsed.has(group.ns)" @click="toggleGroup(group.ns)">
                  {{ collapsed.has(group.ns) ? '展开' : '收起' }}
                  <template #trailing><ChevronDown :size="14" class="transition-transform duration-150" :class="collapsed.has(group.ns) ? '-rotate-90' : ''" /></template>
                </UiButton>
              </template>
            </SectionHeader>

            <UiCard v-if="!collapsed.has(group.ns)" padding="none" class="grid grid-cols-1 gap-x-2 p-1.5 md:grid-cols-2 xl:grid-cols-3">
              <div
                v-for="t in group.items"
                :key="t.id"
                :class="editId === t.id || mergeId === t.id ? 'col-span-full my-1 rounded-lg bg-surface-2 p-2.5' : ''"
              >
                <!-- view row -->
                <div v-if="editId !== t.id && mergeId !== t.id" class="tag-row group flex min-h-11 items-center gap-1 rounded-lg pl-2.5 transition-colors duration-150 hover:bg-surface-2 focus-within:bg-surface-2">
                  <router-link
                    :to="{ path: '/', query: { tag: t.name } }"
                    class="flex min-w-0 flex-1 items-center gap-2 self-stretch rounded-md focus-ring"
                    title="前往媒体库查看此标签作品"
                  >
                    <span class="min-w-0 truncate text-body text-ink">{{ t.name }}</span>
                    <span class="shrink-0 text-caption tabular-nums" :class="(t.count ?? 0) === 0 ? 'text-warning' : 'text-subtle'">{{ t.count ?? 0 }}</span>
                  </router-link>
                  <div class="tag-actions flex shrink-0 items-center">
                    <UiIconButton label="重命名 / 改类别" size="sm" class="pointer-coarse:size-10" @click="startEdit(t)"><Pencil :size="15" /></UiIconButton>
                    <UiIconButton label="合并到另一个标签" size="sm" class="pointer-coarse:size-10" @click="startMerge(t)"><GitMerge :size="15" /></UiIconButton>
                    <UiIconButton label="删除标签" size="sm" class="pointer-coarse:size-10 hover:!bg-danger/12 hover:!text-danger" @click="removeTag(t)"><Trash2 :size="15" /></UiIconButton>
                  </div>
                </div>

                <!-- edit row -->
                <div v-else-if="editId === t.id" class="flex flex-wrap items-center gap-2">
                  <input
                    v-model="editName"
                    aria-label="标签名"
                    autofocus
                    @keydown.enter="saveEdit(t)"
                    @keydown.esc="cancelEdit"
                    :class="[controlClass('md'), 'h-10 min-w-40 flex-1']"
                  />
                  <ThemeSelect v-model="editNs" :options="NAMESPACES" class="w-32 shrink-0" />
                  <div class="flex shrink-0 items-center gap-1">
                    <UiIconButton label="保存" variant="primary" :disabled="busy" @click="saveEdit(t)"><Check :size="16" /></UiIconButton>
                    <UiIconButton label="取消" @click="cancelEdit"><X :size="16" /></UiIconButton>
                  </div>
                </div>

                <!-- merge row -->
                <div v-else class="space-y-2">
                  <p class="truncate text-meta text-muted">合并「<span class="text-ink">{{ t.name }}</span>」到…</p>
                  <div class="flex flex-wrap items-center gap-2">
                    <UiInput v-model="mergeSearch" type="search" placeholder="筛选目标…" aria-label="筛选合并目标" class="w-full sm:w-44">
                      <template #leading><Search :size="14" /></template>
                    </UiInput>
                    <ThemeSelect v-model="mergeTargetId" :options="mergeOptions" class="min-w-0 flex-1 basis-56" />
                    <div class="flex shrink-0 items-center gap-1">
                      <UiIconButton label="确认合并" variant="primary" :disabled="busy || !mergeTargetId" @click="confirmMerge(t)"><Check :size="16" /></UiIconButton>
                      <UiIconButton label="取消" @click="mergeId = null"><X :size="16" /></UiIconButton>
                    </div>
                  </div>
                </div>

                <p v-if="rowError && rowError.id === t.id" role="alert" class="mt-1.5 px-2.5 text-caption text-danger">{{ rowError.msg }}</p>
              </div>
            </UiCard>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
/* Row actions stay quiet until the row is hovered or focused; touch screens always show them. */
@media (hover: hover) and (pointer: fine) {
  .tag-row .tag-actions { opacity: 0; transition: opacity var(--duration-fast) var(--ease-out); }
  .tag-row:hover .tag-actions, .tag-row:focus-within .tag-actions { opacity: 1; }
}
</style>
