<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { Trash2 } from 'lucide-vue-next'
import { authState } from '../auth'
import { audioPlaybackStore } from '../stores/audioPlaybackStore'
import { UiButton, UiModal, UiSpinner } from './ui'
import { executeDiscard, formatBytes, previewDiscard, type DiscardPreview, type DiscardRecord, type DiscardTarget } from '../utils/discardApi'
const target = defineModel<DiscardTarget | null>('target', { required: true })
const emit = defineEmits<{ discarded: [record: DiscardRecord] }>()
const preview = ref<DiscardPreview | null>(null)
const error = ref(''), busy = ref(false), loading = ref(false), acknowledged = ref(false)
let generation = 0, controller: AbortController | null = null
const open = computed({ get: () => !!target.value, set: value => { if (!value && !busy.value) target.value = null } })
const errorText = (err: any) => {
  const detail = err?.response?.data?.detail
  if (detail === 'assistant_operation_busy') return '有扫描、下载或文件操作正在运行，请稍后再试。'
  return typeof detail === 'string' ? detail : '请求失败，请刷新丢弃记录检查操作结果后重试。'
}
const load = async () => {
  const mine = ++generation, selection = target.value
  controller?.abort(); controller = new AbortController()
  preview.value = null; error.value = ''; acknowledged.value = false
  if (!selection) { loading.value = false; return }
  loading.value = true
  try { const result = await previewDiscard(selection, controller.signal); if (mine === generation) preview.value = result }
  catch (err: any) { if (mine === generation && err.code !== 'ERR_CANCELED') error.value = errorText(err) }
  finally { if (mine === generation) loading.value = false }
}
watch(target, () => void load(), { immediate: true })
watch(() => authState.token, () => { generation++; controller?.abort(); target.value = null })
onBeforeUnmount(() => { generation++; controller?.abort() })
const confirm = async () => {
  if (!target.value || !preview.value || busy.value || !acknowledged.value) return
  const selection = { ...target.value }, hash = preview.value.preview_hash, mine = generation
  busy.value = true; error.value = ''
  try {
    const result = await executeDiscard(selection, hash)
    if (mine !== generation) return
    if (audioPlaybackStore.state.media && result.media_ids.includes(audioPlaybackStore.state.media.id)) audioPlaybackStore.stop()
    busy.value = false; target.value = null
    emit('discarded', result)
    window.dispatchEvent(new CustomEvent('he-content-discarded', { detail: result }))
  } catch (err: any) {
    if (mine === generation) { error.value = errorText(err); acknowledged.value = false; preview.value = null }
  } finally { busy.value = false }
}
</script>
<template>
  <UiModal v-model:open="open" title="删除并丢弃" description="确认后删除本地内容，并阻止以后扫描或同步重新下载。" size="md" :hide-close="busy" :close-on-backdrop="!busy">
    <div v-if="loading" class="flex items-center gap-3 py-6 text-muted"><UiSpinner :size="20" />正在确认删除范围…</div>
    <div v-if="error" role="alert" class="rounded-xl border border-danger/30 bg-danger/10 p-3 text-meta text-danger">{{ error }}</div>
    <div v-if="preview" class="space-y-4">
      <div class="rounded-xl border border-line bg-surface p-4">
        <p class="break-words text-body font-semibold text-ink">{{ preview.title }}</p>
        <p class="mt-2 text-meta text-subtle">{{ preview.source_type.toUpperCase() }} · {{ preview.scope }} · {{ preview.media_count }} 项媒体 · {{ formatBytes(preview.file_size) }}</p>
      </div>
      <ul class="max-h-44 space-y-2 overflow-y-auto text-meta text-muted" aria-label="将删除的文件和目录">
        <li v-for="file in preview.files" :key="file.relative_path" class="break-all rounded-lg bg-surface p-2.5">{{ file.relative_path }}<span class="ml-2 text-caption text-subtle">{{ !file.exists ? '文件已不存在' : file.is_directory ? '整个目录' : '文件' }}</span></li>
      </ul>
      <p class="text-meta leading-relaxed text-subtle">{{ preview.message }}</p>
      <label class="flex min-h-11 cursor-pointer items-start gap-3 rounded-xl border border-warning/30 bg-warning/10 p-3 text-meta text-ink">
        <input v-model="acknowledged" type="checkbox" :disabled="busy" class="mt-0.5 size-5 shrink-0 accent-accent" />
        <span>我确认删除以上内容。文件无法恢复；之后可在“丢弃记录”中允许重新下载。</span>
      </label>
    </div>
    <template #footer>
      <UiButton :disabled="busy" @click="open = false">取消</UiButton>
      <UiButton v-if="error && !preview" :loading="loading" @click="load">重新检查</UiButton>
      <UiButton variant="danger" :disabled="!preview || !acknowledged" :loading="busy" @click="confirm"><template #icon><Trash2 :size="16" aria-hidden="true" /></template>{{ busy ? '正在删除…' : '删除并丢弃' }}</UiButton>
    </template>
  </UiModal>
</template>
