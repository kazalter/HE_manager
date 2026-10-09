<script setup lang="ts">
import { computed, ref } from 'vue'
import {
  AlertTriangle,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Pause,
  Play,
  PlayCircle,
  RefreshCw,
  Upload,
  X as XIcon,
} from 'lucide-vue-next'
import { xImportStore } from '../../stores/xImportStore'
import { useXImportPanelData } from '../../composables/useXImportPanelData'
import AutoSyncSection from './AutoSyncSection.vue'
import ExternalSourceLayout from './ExternalSourceLayout.vue'
import { UiBadge, UiButton, UiCard, UiIconButton, UiInput, fieldHintClass, fieldLabelClass, iconButtonClass, type Tone } from '../ui'

const downloadRootPath = ref('')
const cookieString = ref('')
const fileInput = ref<HTMLInputElement | null>(null)
const uploading = ref(false)
const uploadResult = ref<{ parsed: number; new_posts: number; existing_posts: number } | null>(null)
const { failedPosts, failedLoading, fetchFailedPosts, updateAutoSync } = useXImportPanelData(downloadRootPath)

const source = xImportStore.source
const stats = xImportStore.stats
const job = xImportStore.job
const inProgress = xImportStore.inProgress
const errorMessage = xImportStore.errorMessage
const isPaused = xImportStore.isPaused
const postProgress = xImportStore.postProgressPercent
const mediaProgress = xImportStore.mediaProgressPercent
const syncJob = xImportStore.syncJob
const syncInProgress = xImportStore.syncInProgress

const syncStatusLabel = computed(() => {
  if (!syncJob.value) return ''
  const map: Record<string, string> = {
    queued: '排队中',
    running: '同步中',
    completed: '已完成',
    failed: '失败',
    canceled: '已取消',
  }
  return map[syncJob.value.status] || syncJob.value.status
})

const onStartSync = async () => {
  try {
    await xImportStore.startSync()
  } catch (err) {
    console.error('Failed to start X sync:', err)
  }
}

const statusLabel = computed(() => {
  if (!job.value) return ''
  const map: Record<string, string> = {
    queued: '排队中',
    preparing: '准备中',
    running: '导入中',
    paused: '已暂停',
    completed: '已完成',
    failed: '失败',
    canceled: '已取消',
  }
  return map[job.value.status] || job.value.status
})

const jobTone = computed<Tone>(() => {
  const status = job.value?.status
  if (status === 'completed') return 'success'
  if (status === 'failed') return 'danger'
  if (status === 'paused' || status === 'canceled') return 'warning'
  return 'info'
})

const totalPostsRemaining = computed(() => {
  if (!stats.value) return 0
  return stats.value.pending_posts + stats.value.failed_posts
})

const formatTime = (value?: string | null) => {
  if (!value) return '-'
  return new Date(value).toLocaleString()
}

const onPickFile = () => {
  fileInput.value?.click()
}

const onFileChange = async (event: Event) => {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  uploading.value = true
  uploadResult.value = null
  try {
    const trimmed = downloadRootPath.value.trim()
    if (trimmed && (!source.value?.download_root_path || source.value.download_root_path !== trimmed)) {
      await xImportStore.updateSource({ download_root_path: trimmed })
    }
    const res = await xImportStore.uploadArchive(file, trimmed || undefined)
    uploadResult.value = {
      parsed: res.parsed,
      new_posts: res.new_posts,
      existing_posts: res.existing_posts,
    }
    if (res.source.download_root_path) {
      downloadRootPath.value = res.source.download_root_path
    }
  } catch (err) {
    console.error('Failed to upload archive:', err)
  } finally {
    uploading.value = false
    if (input) input.value = ''
  }
}

const saveDownloadRoot = async () => {
  const trimmed = downloadRootPath.value.trim()
  if (!trimmed) {
    xImportStore.setError('请填写下载位置')
    return
  }
  try {
    await xImportStore.updateSource({ download_root_path: trimmed })
    xImportStore.clearError()
  } catch (err: any) {
    xImportStore.setError(err.response?.data?.detail || '保存下载位置失败')
  }
}

const saveCookie = async () => {
  let trimmed = cookieString.value.trim()
  if (!trimmed && !source.value?.cookie_saved) {
    xImportStore.setError('请填写 Cookie')
    return
  }
  
  // Try to parse JSON format (e.g. from extensions)
  if (trimmed.startsWith('[') && trimmed.endsWith(']')) {
    try {
      const arr = JSON.parse(trimmed)
      if (Array.isArray(arr)) {
        trimmed = arr.map(c => `${c.name}=${c.value}`).join('; ') + ';'
      }
    } catch {
      // Fallback to raw string if JSON parsing fails
    }
  }

  try {
    await xImportStore.updateSource({ cookie: trimmed })
    xImportStore.clearError()
    cookieString.value = '' // Clear input after successful save
  } catch (err: any) {
    xImportStore.setError(err.response?.data?.detail || '保存 Cookie 失败')
  }
}

const onStart = async () => {
  if (!source.value) return
  if (!source.value.download_root_path) {
    await saveDownloadRoot()
    if (!source.value.download_root_path) return
  }
  try {
    await xImportStore.startImport()
  } catch (err) {
    console.error('Failed to start X import:', err)
  }
}

const onRetryFailed = async () => {
  if (!source.value) return
  try {
    await xImportStore.startImport({ retryFailedOnly: true })
  } catch (err) {
    console.error('Failed to retry failed posts:', err)
  }
}

const onRetrySkipped = async () => {
  if (!source.value) return
  try {
    await xImportStore.startImport({ retrySkippedOnly: true })
  } catch (err) {
    console.error('Failed to retry skipped posts:', err)
  }
}

const handleAutoSyncUpdate = updateAutoSync
</script>

<template>
  <ExternalSourceLayout
    :status="source?.cookie_saved ? '已登录' : '归档模式'"
    :status-tone="source?.cookie_saved ? 'success' : 'neutral'"
    :meta="source?.last_archive_imported_at ? `归档导入于 ${formatTime(source?.last_archive_imported_at)}` : '尚未上传归档'"
  >
    <template #config>
      <div>
        <label class="block" for="x-download-root"><span :class="fieldLabelClass">下载位置 <span class="text-danger">*</span></span></label>
        <div class="flex gap-2">
          <UiInput id="x-download-root" v-model="downloadRootPath" placeholder="例如 D:\HE\downloads 或 /data/downloads" class="flex-1" />
          <UiButton title="保存" @click="saveDownloadRoot">保存</UiButton>
        </div>
        <p :class="fieldHintClass">文件结构 <code class="font-mono">{root}/x/&lt;作者&gt;/&lt;tweet_id&gt;/</code>，每个 Post 目录写入 info.json。</p>
      </div>

      <div>
        <div class="mb-1.5 flex items-center justify-between gap-2">
          <label for="x-cookie" class="text-meta font-medium text-muted">登录 Cookie <span class="font-normal text-subtle">（可选）</span></label>
          <UiBadge v-if="source?.cookie_saved" tone="success">已保存</UiBadge>
        </div>
        <div class="flex gap-2">
          <UiInput id="x-cookie" v-model="cookieString" type="password" placeholder="auth_token=...; ct0=...;" class="flex-1" />
          <UiButton title="保存" @click="saveCookie">保存</UiButton>
        </div>
        <p :class="fieldHintClass">提供网页端 Cookie 以解除官方 API 对成人内容的访问限制，也用于直接同步收藏。</p>
      </div>

      <div class="space-y-2 border-t border-line pt-5">
        <div class="flex items-center justify-between gap-2">
          <p class="text-body font-medium text-ink">直接同步收藏 <span class="text-meta font-normal text-subtle">无需归档</span></p>
          <UiButton
            v-if="syncJob && syncInProgress"
            size="sm"
            variant="ghost"
            class="hover:!bg-danger/12 hover:!text-danger"
            :disabled="syncJob?.cancel_requested"
            @click="xImportStore.cancelSync()"
          >
            取消
          </UiButton>
        </div>
        <UiButton
          block
          :loading="syncInProgress"
          :disabled="!source?.cookie_saved"
          :title="!source?.cookie_saved ? '需要先保存 cookie' : '通过 GraphQL 接口直接拉取最新喜欢列表，扫到已存在的就停'"
          @click="onStartSync"
        >
          <template #icon><RefreshCw :size="16" aria-hidden="true" /></template>
          {{ syncInProgress ? '同步中…' : '同步最新收藏' }}
        </UiButton>
        <div v-if="syncJob" class="space-y-1 rounded-lg bg-surface-2 px-3 py-2.5 text-caption">
          <div class="flex items-center justify-between gap-2">
            <span class="font-medium text-ink">{{ syncStatusLabel }}</span>
            <span class="ml-2 truncate text-subtle">{{ syncJob.message }}</span>
          </div>
          <p class="text-muted tabular-nums">
            扫描 {{ syncJob.pages_scanned }} 页 · 见到 {{ syncJob.posts_seen }} 条 ·
            <span class="text-success">新增 {{ syncJob.new_posts }}</span> · 已有 {{ syncJob.existing_posts }}
          </p>
          <button
            v-if="!syncInProgress && ['completed','canceled','failed'].includes(syncJob.status)"
            type="button"
            class="rounded-md text-caption text-subtle transition-colors hover:text-ink focus-ring"
            @click="xImportStore.dismissSyncJob()"
          >
            关闭报告
          </button>
        </div>
        <p :class="[fieldHintClass, 'mt-0']">每页 20 条，间隔 2.5 秒；连续两页都是已有的就自动停。只发现新 Post，下载请点「开始导入」。</p>
      </div>

      <div class="space-y-2 border-t border-line pt-5">
        <p class="text-body font-medium text-ink">X 数据归档 (.zip)</p>
        <input ref="fileInput" type="file" accept=".zip" class="hidden" @change="onFileChange" />
        <button
          type="button"
          :disabled="uploading"
          class="flex min-h-11 w-full items-center justify-center gap-2 rounded-lg border border-dashed border-line-strong bg-surface-2 px-3 py-2 text-body font-medium text-muted transition-colors hover:border-accent/50 hover:text-ink focus-ring disabled:opacity-45"
          @click="onPickFile"
        >
          <Upload :size="16" class="shrink-0" :class="uploading ? 'animate-pulse' : ''" aria-hidden="true" />
          <span class="truncate">{{ uploading ? '正在解析归档…' : (source?.last_archive_name ? `重新上传归档 (${source?.last_archive_name})` : '选择 X 数据归档 zip') }}</span>
        </button>
        <p v-if="uploadResult" role="status" class="rounded-lg border border-success/25 bg-success/10 px-3 py-2 text-caption text-success tabular-nums">
          解析 {{ uploadResult.parsed }} 条喜欢，新增 {{ uploadResult.new_posts }}，已存在 {{ uploadResult.existing_posts }}。
        </p>
        <details class="group">
          <summary class="flex cursor-pointer list-none items-center gap-1 rounded-md text-caption text-subtle transition-colors hover:text-ink focus-ring [&::-webkit-details-marker]:hidden">
            <ChevronRight :size="14" class="transition-transform duration-150 group-open:rotate-90" aria-hidden="true" />
            如何获取归档
          </summary>
          <ul class="mt-2 list-disc space-y-1 pl-5 text-caption text-subtle">
            <li>在 X 网页端「设置 → 你的账号 → 下载你的数据归档」申请，通常 24–72 小时后可下载 zip。</li>
            <li>读取 <code class="font-mono text-muted">data/like.js</code>，用公开 syndication 接口拉取每条 Post 的媒体，无需登录态。</li>
            <li>再次上传新归档时，只处理新增和失败的 Post。</li>
            <li>对你的账号不做任何写操作（不点赞、不关注、不发推）。</li>
          </ul>
        </details>
      </div>

      <AutoSyncSection
        v-if="source"
        source-type="x"
        :source-id="source.id"
        :enabled="source.auto_sync_enabled"
        :interval-hours="source.auto_sync_interval_hours"
        :last-run-at="source.auto_sync_last_run_at"
        :next-run-at="source.auto_sync_next_run_at"
        :last-status="source.auto_sync_last_status"
        :last-message="source.auto_sync_last_message"
        :can-enable="!!source.cookie_saved && !!source.download_root_path"
        disable-reason="请先保存 Cookie 并设置下载位置"
        @update="handleAutoSyncUpdate"
      />
    </template>

    <div v-if="errorMessage" role="alert" class="flex items-start gap-3 rounded-lg border border-danger/25 bg-danger/10 py-2 pl-3.5 pr-2 text-meta text-danger">
      <span class="min-w-0 flex-1 py-1">{{ errorMessage }}</span>
      <UiIconButton label="关闭提示" size="sm" class="!text-danger hover:!bg-danger/20" @click="xImportStore.clearError()"><XIcon :size="16" aria-hidden="true" /></UiIconButton>
    </div>

    <div class="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
      <UiCard padding="md">
        <p class="text-meta text-subtle">已发现</p>
        <p class="mt-1 text-title font-semibold text-ink tabular-nums">{{ stats?.total_posts ?? 0 }}</p>
        <p class="mt-1 truncate text-caption text-subtle">条 Post</p>
      </UiCard>
      <UiCard padding="md">
        <p class="text-meta text-subtle">已完成</p>
        <p class="mt-1 text-title font-semibold text-ink tabular-nums">{{ stats?.completed_posts ?? 0 }}</p>
        <p class="mt-1 truncate text-caption text-subtle tabular-nums">{{ stats?.downloaded_media ?? 0 }} 个媒体</p>
      </UiCard>
      <UiCard padding="md">
        <p class="text-meta text-subtle">失败</p>
        <p class="mt-1 text-title font-semibold tabular-nums" :class="stats?.failed_posts ? 'text-danger' : 'text-ink'">{{ stats?.failed_posts ?? 0 }}</p>
        <p class="mt-1 truncate text-caption text-subtle">可重试</p>
      </UiCard>
      <UiCard padding="md">
        <p class="text-meta text-subtle">待处理</p>
        <p class="mt-1 text-title font-semibold text-ink tabular-nums">{{ totalPostsRemaining }}</p>
        <p class="mt-1 truncate text-caption text-subtle">下次导入</p>
      </UiCard>
    </div>

    <UiCard padding="md" class="space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <div class="flex min-w-0 items-center gap-2">
          <h3 class="text-heading font-semibold text-ink">导入任务</h3>
          <UiBadge v-if="job" :tone="jobTone">{{ statusLabel }}</UiBadge>
        </div>
        <div class="flex flex-wrap items-center gap-2">
          <UiButton v-if="job && inProgress && !isPaused" @click="xImportStore.pauseImport()">
            <template #icon><Pause :size="16" aria-hidden="true" /></template>
            暂停
          </UiButton>
          <UiButton v-if="job && isPaused" @click="xImportStore.resumeImport()">
            <template #icon><Play :size="16" aria-hidden="true" /></template>
            继续
          </UiButton>
          <UiButton v-if="job && inProgress" variant="danger" :disabled="job?.cancel_requested" @click="xImportStore.cancelImport()">
            <template #icon><XIcon :size="16" aria-hidden="true" /></template>
            取消
          </UiButton>
          <UiButton variant="primary" :disabled="inProgress || !source?.download_root_path || !stats?.total_posts" @click="onStart">
            <template #icon><PlayCircle :size="16" aria-hidden="true" /></template>
            开始导入
          </UiButton>
        </div>
      </div>

      <div class="flex flex-wrap gap-2">
        <UiButton size="sm" :disabled="inProgress || !stats?.failed_posts" @click="onRetryFailed">
          <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
          重试失败 <span class="tabular-nums text-subtle">{{ stats?.failed_posts ?? 0 }}</span>
        </UiButton>
        <UiButton
          size="sm"
          :disabled="inProgress || !stats?.skipped_posts"
          title="重跑早先被标记为跳过的 Post（多为成人内容，需 cookie 才能拉取）"
          @click="onRetrySkipped"
        >
          <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
          重试跳过 <span class="tabular-nums text-subtle">{{ stats?.skipped_posts ?? 0 }}</span>
        </UiButton>
      </div>

      <div v-if="job" class="space-y-4 border-t border-line pt-4">
        <p v-if="job.message" class="truncate text-meta text-muted">{{ job.message }}</p>

        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-meta text-muted tabular-nums">
            <span>Post 进度 {{ job.completed_posts + job.skipped_posts + job.failed_posts }} / {{ job.total_posts }}</span>
            <span>{{ postProgress }}%</span>
          </div>
          <div class="h-1 overflow-hidden rounded-sm bg-surface-3">
            <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: `${postProgress}%` }"></div>
          </div>
        </div>

        <div class="space-y-1.5">
          <div class="flex items-center justify-between text-meta text-muted tabular-nums">
            <span>媒体下载 {{ job.media_downloaded }} / {{ job.media_total }}</span>
            <span>{{ mediaProgress }}%</span>
          </div>
          <div class="h-1 overflow-hidden rounded-sm bg-surface-3">
            <div class="h-full rounded-sm bg-accent transition-[width] duration-200" :style="{ width: `${mediaProgress}%` }"></div>
          </div>
        </div>

        <dl class="grid grid-cols-2 gap-2 sm:grid-cols-4">
          <div class="rounded-lg bg-surface-2 px-3 py-2">
            <dt class="text-caption text-subtle">含媒体 Post</dt>
            <dd class="mt-0.5 text-body font-medium text-ink tabular-nums">{{ job.media_posts }}</dd>
          </div>
          <div class="rounded-lg bg-surface-2 px-3 py-2">
            <dt class="text-caption text-subtle">跳过</dt>
            <dd class="mt-0.5 text-body font-medium text-ink tabular-nums">{{ job.skipped_posts }}</dd>
          </div>
          <div class="rounded-lg bg-surface-2 px-3 py-2">
            <dt class="text-caption text-subtle">失败</dt>
            <dd class="mt-0.5 text-body font-medium text-ink tabular-nums">{{ job.failed_posts }}</dd>
          </div>
          <div class="rounded-lg bg-surface-2 px-3 py-2">
            <dt class="text-caption text-subtle">媒体失败</dt>
            <dd class="mt-0.5 text-body font-medium text-ink tabular-nums">{{ job.media_failed }}</dd>
          </div>
        </dl>

        <p v-if="job.current_post_id || job.current_author" class="truncate text-meta text-subtle">
          当前：@{{ job.current_author || '?' }} / {{ job.current_post_id }}
          <span v-if="job.current_file">· {{ job.current_file }}</span>
        </p>

        <div v-if="['completed', 'canceled', 'failed'].includes(job.status)" class="space-y-1 rounded-lg bg-surface-2 p-3">
          <p class="flex items-center gap-2 text-meta font-medium text-ink">
            <CheckCircle2 v-if="job.status === 'completed'" :size="15" class="text-success" aria-hidden="true" />
            <AlertTriangle v-else :size="15" class="text-warning" aria-hidden="true" />
            导入结果报告
          </p>
          <p class="text-caption text-muted tabular-nums">
            扫描 {{ job.scanned_posts }} 个 Post · 含媒体 {{ job.media_posts }} ·
            成功 {{ job.completed_posts }} · 跳过 {{ job.skipped_posts }} · 失败 {{ job.failed_posts }}
          </p>
          <p class="text-caption text-subtle tabular-nums">媒体下载 {{ job.media_downloaded }} / {{ job.media_total }}（失败 {{ job.media_failed }}）</p>
          <button
            v-if="!inProgress"
            type="button"
            class="mt-1 rounded-md text-caption text-subtle transition-colors hover:text-ink focus-ring"
            @click="xImportStore.dismissJob()"
          >
            关闭报告
          </button>
        </div>
      </div>

      <p v-else class="text-meta text-subtle">
        上传归档并设置好下载位置后，点击「开始导入」。任务在后台运行，切换页面也会继续。
      </p>
    </UiCard>

    <UiCard padding="none" class="overflow-hidden">
      <div class="flex items-center justify-between gap-3 px-4 py-3 sm:px-5">
        <h3 class="text-body font-semibold text-ink">失败项 <span class="ml-1 text-meta font-normal text-subtle tabular-nums">{{ failedPosts.length }}</span></h3>
        <UiButton size="sm" variant="ghost" :loading="failedLoading" @click="fetchFailedPosts">
          <template #icon><RefreshCw :size="14" aria-hidden="true" /></template>
          刷新
        </UiButton>
      </div>
      <p v-if="failedPosts.length === 0" class="border-t border-line px-4 py-6 text-center text-meta text-subtle sm:px-5">没有失败项</p>
      <ul v-else class="max-h-80 divide-y divide-line overflow-y-auto border-t border-line">
        <li v-for="post in failedPosts" :key="post.id" class="flex items-center gap-3 px-4 py-2.5 sm:px-5">
          <div class="min-w-0 flex-1">
            <p class="truncate text-meta font-medium text-ink">@{{ post.author_screen_name || '?' }} <span class="font-normal text-subtle tabular-nums">· {{ post.tweet_id }}</span></p>
            <p class="truncate text-caption text-danger">{{ post.error_message || '未知错误' }}</p>
          </div>
          <a :href="post.url" target="_blank" rel="noreferrer" :class="iconButtonClass('ghost', 'sm')" aria-label="打开原帖" title="打开原帖">
            <ExternalLink :size="15" aria-hidden="true" />
          </a>
        </li>
      </ul>
    </UiCard>

    <UiCard v-if="job?.errors?.length" padding="none" class="overflow-hidden">
      <h3 class="px-4 py-3 text-body font-semibold text-ink sm:px-5">错误日志</h3>
      <ul class="max-h-56 space-y-1 overflow-y-auto border-t border-line px-4 py-3 text-caption text-muted sm:px-5">
        <li v-for="err in job.errors.slice().reverse()" :key="`${err.tweet_id}-${err.at}`" class="truncate">
          <span class="text-subtle tabular-nums">{{ err.at.slice(11, 19) }}</span>
          <span v-if="err.tweet_id" class="tabular-nums"> · {{ err.tweet_id }}</span>
          · <span class="text-warning">{{ err.message }}</span>
        </li>
      </ul>
    </UiCard>
  </ExternalSourceLayout>
</template>
