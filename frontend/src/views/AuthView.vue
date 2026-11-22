<script setup lang="ts">
import ColorModeToggle from '../components/ColorModeToggle.vue'
import { computed, ref, useId } from 'vue'
import { AlertCircle, AlertTriangle, Film, Book, Headphones, Image as ImageIcon, ShieldCheck } from 'lucide-vue-next'
import { bootstrapAdmin, login, retryAuth } from '../auth'
import UiButton from '../components/ui/UiButton.vue'
import { controlClass, fieldLabelClass } from '../components/ui/classes'

const props = defineProps<{
  hasUsers: boolean
  startupError?: string
}>()

const id = useId()
const username = ref('')
const password = ref('')
const loading = ref(false), retrying = ref(false)
const retry = async () => { retrying.value = true; try { await retryAuth() } finally { retrying.value = false } }
const errorMessage = ref('')

const modeText = computed(() => props.hasUsers ? '登录' : '创建管理员')
const hintText = computed(() => props.hasUsers ? '输入账号密码进入你的个人媒体库' : '第一次使用，请先创建管理员账号')
const inputClass = controlClass('lg')

const submit = async () => {
  if (!username.value.trim() || !password.value) return
  loading.value = true
  errorMessage.value = ''
  try {
    if (props.hasUsers) {
      await login(username.value.trim(), password.value)
    } else {
      await bootstrapAdmin(username.value.trim(), password.value)
    }
  } catch (err: any) {
    errorMessage.value = err.response?.data?.detail || err.message || `${modeText.value}失败`
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="he-auth-view relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-background px-4 py-10 text-ink">
    <div class="absolute right-4 top-4 z-20"><ColorModeToggle compact :show-tooltip="false" /></div>
    <div class="he-auth-ambient" aria-hidden="true"></div>

    <div class="relative z-10 grid w-full max-w-[840px] items-stretch overflow-hidden rounded-3xl squircle border border-line bg-surface shadow-modal lg:grid-cols-[1.05fr_1fr]">
      <!-- Editorial left showcase panel (desktop) -->
      <aside class="hidden lg:flex flex-col justify-between border-r border-line/80 bg-surface-2/60 p-8 relative overflow-hidden">
        <div class="pointer-events-none absolute -left-24 -top-24 size-72 rounded-full bg-accent/15 blur-3xl" aria-hidden="true"></div>
        <div class="relative z-10 flex items-center gap-3">
          <div class="grid size-10 place-items-center rounded-xl squircle bg-accent text-sm font-bold tracking-wider text-on-accent shadow-[inset_0_1px_0_rgb(255_255_255/0.25),0_4px_12px_-3px_rgb(var(--color-accent)/0.55)]">HE</div>
          <div>
            <p class="text-body font-semibold leading-tight text-ink">HE Manager</p>
            <p class="text-caption text-subtle">个人自托管多媒体中心</p>
          </div>
        </div>

        <div class="relative z-10 space-y-5 my-8">
          <h2 class="text-title font-semibold leading-snug text-ink">沉浸、克制、全能的私人媒体画廊</h2>
          <ul class="space-y-3 text-meta text-muted">
            <li class="flex items-center gap-3">
              <span class="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-surface text-accent-glow" aria-hidden="true"><Film :size="15" /></span>
              <span>本地视频、断点续播与智能缩略图预览</span>
            </li>
            <li class="flex items-center gap-3">
              <span class="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-surface text-accent-glow" aria-hidden="true"><Book :size="15" /></span>
              <span>单双页与长条漫阅读，自适应手机与桌面</span>
            </li>
            <li class="flex items-center gap-3">
              <span class="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-surface text-accent-glow" aria-hidden="true"><Headphones :size="15" /></span>
              <span>ASMR 音频歌单与全局悬浮播放条</span>
            </li>
            <li class="flex items-center gap-3">
              <span class="grid size-8 shrink-0 place-items-center rounded-lg border border-line bg-surface text-accent-glow" aria-hidden="true"><ImageIcon :size="15" /></span>
              <span>多标签组合筛选、创作者聚合与相似去重</span>
            </li>
          </ul>
        </div>

        <p class="relative z-10 flex items-center gap-2 text-caption text-subtle">
          <ShieldCheck :size="14" class="text-success" aria-hidden="true" />
          <span>数据与索引完全保留在本地服务器</span>
        </p>
      </aside>

      <!-- Sign-in form -->
      <form
        class="relative z-10 flex flex-col justify-center space-y-6 p-6 sm:p-8 lg:p-10"
        @submit.prevent="submit"
      >
        <div>
          <div class="mb-6 flex items-center gap-3 lg:hidden">
            <div class="grid size-10 place-items-center rounded-xl squircle bg-accent text-sm font-bold tracking-wider text-on-accent shadow-[0_4px_12px_-3px_rgb(var(--color-accent)/0.55)]">HE</div>
            <div class="min-w-0">
              <p class="text-body font-semibold leading-tight text-ink">HE Manager</p>
              <p class="text-caption text-subtle">个人媒体中心</p>
            </div>
          </div>
          <h1 class="text-title font-semibold text-ink">{{ modeText }}</h1>
          <p class="mt-1.5 text-meta text-subtle">{{ hintText }}</p>
        </div>

        <div v-if="startupError" role="status" class="flex items-start gap-2.5 rounded-xl border border-warning/30 bg-warning/10 px-3.5 py-3 text-meta leading-relaxed text-warning">
          <AlertTriangle :size="16" class="mt-0.5 shrink-0" aria-hidden="true" />
          <div class="min-w-0 flex-1">
            <p>{{ startupError }}</p>
            <UiButton class="mt-2.5" size="sm" :loading="retrying" @click="retry">重新检查连接</UiButton>
          </div>
        </div>

        <div class="space-y-4">
          <div class="block">
            <label :for="`${id}-user`" :class="fieldLabelClass">用户名</label>
            <input
              :id="`${id}-user`"
              v-model="username"
              required
              autocomplete="username"
              placeholder="请输入用户名"
              :class="inputClass"
            />
          </div>

          <div class="block">
            <label :for="`${id}-pass`" :class="fieldLabelClass">密码</label>
            <input
              :id="`${id}-pass`"
              v-model="password"
              type="password"
              required
              autocomplete="current-password"
              placeholder="请输入密码"
              :class="inputClass"
            />
          </div>
        </div>

        <div v-if="errorMessage" role="alert" class="flex items-start gap-2.5 rounded-xl border border-danger/30 bg-danger/10 px-3.5 py-3 text-meta leading-relaxed text-danger">
          <AlertCircle :size="16" class="mt-0.5 shrink-0" aria-hidden="true" />
          <span>{{ errorMessage }}</span>
        </div>

        <UiButton
          type="submit"
          variant="primary"
          size="lg"
          block
          :loading="loading"
          :disabled="!username.trim() || !password"
        >
          {{ loading ? '正在安全连接' : modeText }}
        </UiButton>
      </form>
    </div>
  </div>
</template>

<style>
.he-auth-ambient {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background:
    radial-gradient(1200px 680px at 50% -20% var(--in-oklab), rgb(var(--color-accent) / 0.14), rgb(var(--color-accent) / 0.04) 45%, transparent 78%),
    radial-gradient(800px 500px at 85% 95% var(--in-oklab), rgb(var(--color-accent-glow) / 0.06), transparent 72%);
}
</style>
