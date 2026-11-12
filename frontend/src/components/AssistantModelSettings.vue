<script setup lang="ts">
import { onMounted, ref } from 'vue'
import axios from 'axios'
import { API_BASE_URL } from '../config'
import type { AiRecommendationStatus } from '../types'
import { SectionHeader, UiButton, UiCard, controlClass, fieldLabelClass } from './ui'
const status = ref<AiRecommendationStatus | null>(null)
const model = ref('deepseek-chat')
const baseUrl = ref('https://api.deepseek.com')
const key = ref('')
const busy = ref(false)
const message = ref('')
function update(value: AiRecommendationStatus) { status.value = value; model.value = value.model; baseUrl.value = value.base_url }
onMounted(async () => {
  try { update((await axios.get<AiRecommendationStatus>(`${API_BASE_URL}/ai/recommendations/status`)).data) }
  catch { message.value = '无法读取模型配置' }
})
async function save(clear = false) {
  if (clear && !window.confirm('确定清除保存的 API Key 吗？助手可能无法连接模型。')) return
  busy.value = true
  message.value = ''
  try {
    const payload = clear ? { clear_api_key: true } : {
      api_key: key.value.trim() || undefined, model: model.value.trim(), base_url: baseUrl.value.trim(),
    }
    update((await axios.put<AiRecommendationStatus>(`${API_BASE_URL}/ai/recommendations/config`, payload)).data)
    key.value = ''
    message.value = clear ? '已清除保存的 API Key' : '已保存配置'
  } catch { message.value = '保存失败，请检查配置后重试' }
  finally { busy.value = false }
}
</script>
<template>
  <section>
    <SectionHeader title="助手默认模型" description="使用默认模型配置时，媒体库助手会使用这里的设置；单独配置的助手模型不受影响。" />
    <UiCard padding="md" class="space-y-4">
      <p class="text-meta text-subtle">{{ status?.deepseek_configured ? '已配置 API Key' : '尚未配置 API Key' }}<span v-if="status?.env_key_present">（由环境变量提供）</span></p>
      <label class="block"><span :class="fieldLabelClass">API 地址</span><input v-model="baseUrl" :class="controlClass" type="url" autocomplete="url" /></label>
      <label class="block"><span :class="fieldLabelClass">模型</span><input v-model="model" :class="controlClass" autocomplete="off" /></label>
      <label class="block"><span :class="fieldLabelClass">API Key</span><input v-model="key" :class="controlClass" type="password" autocomplete="new-password" placeholder="留空以保留已保存的密钥" /></label>
      <div class="flex flex-wrap items-center gap-3"><UiButton variant="primary" :loading="busy" @click="save(false)">保存</UiButton><UiButton v-if="status?.key_saved" :disabled="busy" @click="save(true)">清除密钥</UiButton><span role="status" class="text-meta text-subtle">{{ message }}</span></div>
    </UiCard>
  </section>
</template>
