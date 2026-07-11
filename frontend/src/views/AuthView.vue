<script setup lang="ts">
import { computed, ref } from 'vue'
import { bootstrapAdmin, login } from '../auth'

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
  <div class="min-h-screen w-full bg-background text-white flex items-center justify-center px-6 relative overflow-hidden">
    <!-- Apple-style Dynamic Ambient Glow -->
    <div class="fixed inset-0 pointer-events-none overflow-hidden z-0">
      <div class="glow-sphere sphere-1"></div>
      <div class="glow-sphere sphere-2"></div>
      <div class="glow-sphere sphere-3"></div>
    </div>

    <form
      @submit.prevent="submit"
      class="relative z-10 w-full max-w-sm bg-white/[0.02] backdrop-blur-3xl border border-white/8 rounded-3xl p-8 shadow-[inset_0_1px_1px_rgba(255,255,255,0.08),0_24px_50px_-12px_rgba(0,0,0,0.5)] space-y-6"
    >
      <div class="text-center sm:text-left">
        <div class="w-12 h-12 rounded-2xl bg-gradient-to-tr from-accent to-indigo-400 text-white font-black flex items-center justify-center mx-auto sm:mx-0 mb-5 shadow-lg shadow-accent/25">
          <span class="text-base tracking-wide">HE</span>
        </div>
        <h1 class="text-2xl font-black tracking-tight text-white/95">{{ modeText }}</h1>
        <p class="text-xs text-white/45 mt-1.5 font-medium leading-relaxed">{{ hintText }}</p>
      </div>

      <div v-if="startupError" class="text-xs text-amber-200 bg-amber-500/10 border border-amber-500/20 rounded-2xl px-4 py-3 leading-relaxed shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
        {{ startupError }}
      </div>

      <div class="space-y-4">
        <label class="block space-y-2">
          <span class="text-xs font-bold text-white/55 tracking-wider uppercase">用户名</span>
          <input
            v-model="username"
            autocomplete="username"
            placeholder="请输入用户名"
            class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:bg-white/10 focus:border-accent/30 shadow-[inset_0_1px_2px_rgba(0,0,0,0.15)] transition-all duration-300"
          />
        </label>

        <label class="block space-y-2">
          <span class="text-xs font-bold text-white/55 tracking-wider uppercase">密码</span>
          <input
            v-model="password"
            type="password"
            autocomplete="current-password"
            placeholder="请输入密码"
            class="w-full bg-white/5 border border-white/10 rounded-xl px-4 py-3 text-sm text-white placeholder-white/20 focus:outline-none focus:ring-2 focus:ring-accent/40 focus:bg-white/10 focus:border-accent/30 shadow-[inset_0_1px_2px_rgba(0,0,0,0.15)] transition-all duration-300"
          />
        </label>
      </div>

      <div v-if="errorMessage" class="text-xs text-red-200 bg-red-500/10 border border-red-500/20 rounded-2xl px-4 py-3 leading-relaxed shadow-[inset_0_1px_0_rgba(255,255,255,0.02)]">
        {{ errorMessage }}
      </div>

      <button
        type="submit"
        :disabled="loading || !username.trim() || !password"
        class="w-full h-12 rounded-xl bg-gradient-to-r from-indigo-500 via-indigo-600 to-purple-600 text-white font-black hover:opacity-95 active:scale-[0.98] disabled:opacity-40 disabled:scale-100 disabled:cursor-not-allowed shadow-lg shadow-indigo-600/20 transition-all duration-300 cursor-pointer"
      >
        <span v-if="loading" class="flex items-center justify-center gap-2">
          <svg class="animate-spin h-4 w-4 text-white" fill="none" viewBox="0 0 24 24">
            <circle class="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" stroke-width="4"></circle>
            <path class="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          正在安全连接
        </span>
        <span v-else>{{ modeText }}</span>
      </button>
    </form>
  </div>
</template>

<style>
.glow-sphere {
  position: absolute;
  border-radius: 50%;
  filter: blur(140px);
  opacity: 0.15;
  pointer-events: none;
  mix-blend-mode: screen;
}

.sphere-1 {
  top: -20%;
  left: -10%;
  width: 60%;
  height: 60%;
  background: radial-gradient(circle, #6366f1 0%, transparent 70%);
  animation: float-slow 25s infinite alternate ease-in-out;
}

.sphere-2 {
  bottom: -15%;
  right: -10%;
  width: 55%;
  height: 55%;
  background: radial-gradient(circle, #8b5cf6 0%, transparent 70%);
  animation: float-slow-reverse 20s infinite alternate ease-in-out;
}

.sphere-3 {
  top: 30%;
  right: 15%;
  width: 40%;
  height: 40%;
  background: radial-gradient(circle, #06b6d4 0%, transparent 70%);
  animation: float-slow-alt 30s infinite alternate ease-in-out;
}
</style>
