<script setup lang="ts">
import { computed, ref, watch, onBeforeUnmount } from 'vue'
import { FolderTree, FileText, Eye, Users, ListChecks, ScrollText, HardDrive, Settings, Copy, Check, ChevronDown } from 'lucide-vue-next'
import type { Component } from 'vue'
import { UiButton, UiCard } from '../ui'
import { fetchPreview, assistantErrorText } from '../../utils/assistantApi'
import { authIdentity } from '../../auth'
import type { ToolResultDTO } from '../../types/assistant'
const props = defineProps<{ results: ToolResultDTO[] }>()
const labels: Record<string, string> = { list_directory: '目录文件', read_text: '文件内容', get_media_preview: '媒体预览', list_creators: '作者', get_creator_detail: '作者资料', list_tasks: '后台任务', get_task_detail: '任务状态', read_logs: '运行日志', get_project_status: '存储与备份', get_project_settings: '项目设置' }
const icons: Record<string, Component> = { list_directory: FolderTree, read_text: FileText, get_media_preview: Eye, list_creators: Users, get_creator_detail: Users, list_tasks: ListChecks, get_task_detail: ListChecks, read_logs: ScrollText, get_project_status: HardDrive, get_project_settings: Settings }
const fieldLabels: Record<string, string> = { path: '路径', display_name: '目录', download_root_name: '下载目录', name: '名称', key: '作者编号', media_count: '媒体数量', media_id: '媒体编号', media_type: '媒体类型', page_count: '页数', page_index: '页码', total: '总数', health: '运行状态', storage: '磁盘', backup: '备份', backup_count: '备份数量', free_bytes: '可用空间', total_bytes: '总空间', size_bytes: '大小', folder_id: '目录编号', id: '编号', task_id: '任务编号', kind: '任务类型', status: '状态', summary: '说明', code: '事件', timestamp: '时间', service: '服务', level: '级别', created_at: '创建时间', finished_at: '完成时间', modified_at: '修改时间', source_path: '源路径', destination_path: '目标路径', scan_mode: '扫描范围', thumbnail_enabled: '生成缩略图', thumbnail_interval: '缩略图间隔', available: '可读取', notice: '说明', folders: '目录设置', download_root_path: '下载目录', auto_sync_enabled: '自动同步', auto_sync_interval_hours: '同步间隔（小时）', next_run_at: '下次同步', source_type: '数据源类型', items: '条目', total_count: '任务总数', completed_count: '完成数量', failed_count: '失败数量', progress_count: '处理数量', progress: '进度', offset: '本页起点', has_more: '还有后续', next_offset: '下页起点', next_offset_bytes: '后续字节位置', relative_path: '相对路径', encoding: '编码', object_id: '对象', request_id: '错误编号', entry_type: '类型' }
const valueLabels: Record<string, string> = { queued: '等待中', running: '执行中', completed: '完成', failed: '失败', interrupted: '中断', needs_recovery: '需要恢复', file: '文件', directory: '目录', link: '链接', ok: '正常', video: '视频', image: '图片', manga: '漫画', audio: '音频', assistant: '管家', scan: '扫描', download: '下载', auto_sync: '自动同步', runtime: '运行', import: '导入' }
const calls = computed(() => props.results.filter(x => x.tool_name in labels))
function display(value: unknown): string {
  if (value === null) return '暂无'
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'string') return valueLabels[value] || value
  if (Array.isArray(value)) return value.map(display).join('\n') || '暂无记录'
  if (typeof value === 'object') return Object.entries(value as Record<string, unknown>).filter(([k]) => !['cursor', 'next_cursor', 'preview_path', 'analysis_supported', 'analysis_performed'].includes(k)).map(([k, v]) => (fieldLabels[k] || k) + '：' + display(v)).join('\n')
  return String(value)
}
const copiedId = ref('')
let copyTimer: ReturnType<typeof setTimeout> | undefined
async function copyText(call: ToolResultDTO) {
  const text = call.tool_name === 'read_text' ? String(call.result.text ?? '') : display(call.result)
  if (!text || typeof navigator === 'undefined' || !navigator.clipboard?.writeText) return
  try {
    await navigator.clipboard.writeText(text)
    copiedId.value = call.tool_call_id
    clearTimeout(copyTimer)
    copyTimer = setTimeout(() => { copiedId.value = '' }, 1600)
  } catch { /* Clipboard permission denied */ }
}
const preview = ref(''), mime = ref(''), busy = ref(''), error = ref('')
let request = new AbortController(), alive = true
function reset() { request.abort(); request = new AbortController(); if (preview.value) URL.revokeObjectURL(preview.value); preview.value = ''; mime.value = ''; busy.value = ''; error.value = '' }
async function open(call: ToolResultDTO) {
  reset(); const controller = request; busy.value = call.tool_call_id
  try {
    const blob = await fetchPreview(String(call.result.preview_path), controller.signal)
    if (!alive || controller.signal.aborted) return
    mime.value = blob.type; preview.value = URL.createObjectURL(blob)
  } catch (e) { if (alive && !controller.signal.aborted) error.value = assistantErrorText(e) }
  finally { if (alive && !controller.signal.aborted) busy.value = '' }
}
watch(() => props.results, reset)
watch(() => authIdentity(), reset)
onBeforeUnmount(() => { alive = false; clearTimeout(copyTimer); reset() })
</script>
<template>
  <section v-if="calls.length" aria-label="项目查询结果" class="min-w-0 space-y-3">
    <UiCard v-for="call in calls" :key="call.tool_call_id" padding="sm" class="min-w-0">
      <div class="mb-3 flex flex-wrap items-center justify-between gap-2 border-b border-line/70 pb-2.5">
        <h3 class="flex items-center gap-2 text-sm font-semibold text-ink sm:text-base">
          <span class="grid size-7 shrink-0 place-items-center rounded-lg bg-accent/12 text-accent" aria-hidden="true">
            <component :is="icons[call.tool_name]" :size="15" />
          </span>
          {{ labels[call.tool_name] }}
          <span v-if="call.result.total !== undefined" class="rounded-full bg-surface-2 px-2 py-0.5 text-xs font-medium tabular-nums text-subtle">{{ call.result.total }} 项</span>
        </h3>
        <button
          v-if="call.tool_name !== 'get_media_preview'"
          type="button"
          class="inline-flex min-h-8 items-center gap-1 rounded-full border border-line bg-surface-2 px-2.5 py-1 text-xs font-medium text-muted transition-colors duration-150 hover:border-accent/35 hover:text-ink focus-ring"
          @click="copyText(call)"
        >
          <Check v-if="copiedId === call.tool_call_id" :size="13" class="text-accent" aria-hidden="true" />
          <Copy v-else :size="13" aria-hidden="true" />
          <span>{{ copiedId === call.tool_call_id ? '已复制' : '复制' }}</span>
        </button>
      </div>
      <pre v-if="call.tool_name === 'read_text'" class="custom-scrollbar max-h-96 overflow-y-auto whitespace-pre-wrap rounded-xl border border-line/80 bg-surface-2/80 p-3 font-sans text-sm leading-relaxed text-ink [overflow-wrap:anywhere]">{{ call.result.text }}</pre>
      <template v-else-if="call.tool_name === 'get_media_preview'">
        <p class="mb-3 text-sm leading-relaxed text-muted">{{ call.result.notice }}</p>
        <UiButton class="min-h-10" size="sm" :loading="busy === call.tool_call_id" @click="open(call)">查看预览</UiButton>
      </template>
      <template v-else>
        <details class="assistant-result-details rounded-xl border border-line/80 bg-surface-2/40 px-3 py-1">
          <summary class="flex min-h-10 cursor-pointer items-center justify-between gap-2 rounded-lg text-sm font-medium text-muted hover:text-ink focus-ring">
            <span>查看结果<span v-if="call.result.total !== undefined"> · {{ call.result.total }} 项</span></span>
            <ChevronDown :size="15" class="assistant-details-chevron shrink-0 text-subtle" aria-hidden="true" />
          </summary>
          <pre class="custom-scrollbar mb-2 mt-1 max-h-96 overflow-y-auto whitespace-pre-wrap rounded-xl border border-line/70 bg-surface-2 p-3 font-sans text-sm leading-relaxed text-ink [overflow-wrap:anywhere]">{{ display(call.result) }}</pre>
        </details>
      </template>
      <p v-if="call.result.has_more || call.result.truncated" class="mt-3 text-xs text-subtle">当前展示部分结果，可让管家继续查询下一页。</p>
    </UiCard>
    <div v-if="preview" class="rounded-2xl border border-line bg-surface-2/80 p-3">
      <img v-if="mime.startsWith('image/')" :src="preview" alt="媒体预览" class="mx-auto max-h-[60vh] max-w-full rounded-xl" />
      <video v-else-if="mime.startsWith('video/')" :src="preview" controls class="w-full rounded-xl" />
      <audio v-else :src="preview" controls class="w-full" />
      <UiButton variant="ghost" class="mt-2 min-h-10" size="sm" @click="reset">关闭预览</UiButton>
    </div>
    <p v-if="error" role="alert" class="rounded-xl border border-danger/30 bg-danger/8 px-3 py-2 text-sm text-danger">{{ error }}</p>
  </section>
</template>
<style scoped>
.assistant-result-details .assistant-details-chevron {
  transition: transform 200ms var(--ease-snappy);
}
.assistant-result-details[open] .assistant-details-chevron {
  transform: rotate(180deg);
}
@media (prefers-reduced-motion: reduce) {
  .assistant-result-details .assistant-details-chevron { transition: none; }
}
</style>
