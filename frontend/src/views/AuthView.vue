<script setup lang="ts">
import { computed, ref } from 'vue'
import { bootstrapAdmin, login } from '../auth'
import UiButton from '../components/ui/UiButton.vue'
import { controlClass, fieldLabelClass } from '../components/ui/classes'

const props = defineProps<{
  hasUsers: boolean
  startupError?: string
}>()

const username = ref('')
const password = ref('')
const loading = ref(false)
const errorMessage = ref('')

const modeText = computed(() => props.hasUsers ? '登录' : '创建管理员')
const hintText = computed(() => props.hasUsers ? '输入账号密码进入媒体库' : '第一次使用，请先创建管理员账号')
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
    errorMessage.value = err.response?.data?.detail || `${modeText.value}失败`
  } finally {
    loading.value = false
  }
}
</script>

<template>
  <div class="he-auth-view relative flex min-h-screen w-full items-center justify-center overflow-hidden bg-background px-4 text-ink">
    <div class="he-auth-ambient" aria-hidden="true"></div>

    <form
      class="relative z-10 w-full max-w-[380px] space-y-6 rounded-3xl border border-line bg-surface p-6 shadow-pop sm:p-8"
      @submit.prevent="submit"
    >
      <div>
        <div class="mb-6 flex items-center gap-3">
          <div class="grid size-10 place-items-center rounded-xl bg-accent text-sm font-semibold tracking-wide text-on-accent">HE</div>
          <div class="min-w-0">
            <p class="text-body font-semibold leading-tight text-ink">HE Manager</p>
            <p class="text-caption text-subtle">个人媒体中心</p>
          </div>
        </div>
        <h1 class="text-title font-semibold text-ink">{{ modeText }}</h1>
        <p class="mt-1.5 text-meta text-subtle">{{ hintText }}</p>
      </div>

      <div v-if="startupError" role="status" class="rounded-lg border border-warning/25 bg-warning/10 px-3.5 py-3 text-meta leading-relaxed text-warning">
        {{ startupError }}
      </div>

      <div class="space-y-4">
        <label class="block">
          <span :class="fieldLabelClass">用户名</span>
          <input
            v-model="username"
            autocomplete="username"
            placeholder="请输入用户名"
            :class="inputClass"
          />
        </label>

        <label class="block">
          <span :class="fieldLabelClass">密码</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            :class="inputClass"
          />
        </label>
      </div>

      <div v-if="errorMessage" role="alert" class="rounded-lg border border-danger/25 bg-danger/10 px-3.5 py-3 text-meta leading-relaxed text-danger">
        {{ errorMessage }}
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
</template>

<style>
.he-auth-ambient {
  position: fixed;
  inset: 0;
  pointer-events: none;
  background: radial-gradient(1400px 760px at 50% -25%, rgb(var(--color-accent) / 0.11), rgb(var(--color-accent) / 0.04) 45%, transparent 80%);
}
</style>
