<script setup lang="ts">
import { onBeforeUnmount, ref, watch } from 'vue'
import axios from 'axios'
import { API_BASE_URL } from '../config'
import { authHeaders, authIdentity } from '../auth'
import { desktopBridge } from '../desktop'
import type { Media } from '../types'
import type { DiscardRecord } from '../utils/discardApi'
import MediaDetail from './MediaDetail.vue'
import { EmptyState, LoadingState, UiButton } from './ui'
const props = defineProps<{
  initialMedia: Media
  allMedia: Media[]
  verifiedForOpen?: boolean
  hasAdjacentMediaPage?: (direction: -1 | 1) => boolean
  loadAdjacentMediaPage?: (direction: -1 | 1) => Promise<boolean>
}>()
const emit = defineEmits<{ close: []; updated: [media: Media]; navigate: [media: Media]; discarded: [record: DiscardRecord] }>()
const verified = ref<Media | null>(null), error = ref('')
let controller: AbortController | undefined, epoch = 0
async function verify() {
  controller?.abort()
  const current = ++epoch, identity = authIdentity(), mediaId = props.initialMedia.id
  verified.value = null; error.value = ''
  if (!desktopBridge || props.verifiedForOpen) { verified.value = props.initialMedia; return }
  controller = new AbortController()
  try {
    const response = await axios.get(`${API_BASE_URL}/media/${mediaId}`, { signal: controller.signal, headers: authHeaders() })
    if (current !== epoch || identity !== authIdentity()) return
    if (response.data?.id !== mediaId) throw new Error('服务器返回的作品信息无效')
    verified.value = response.data
    emit('updated', response.data)
  } catch (failure) {
    if (current !== epoch || identity !== authIdentity() || axios.isCancel(failure)) return
    error.value = failure instanceof Error ? failure.message : '无法打开作品，请重试'
  }
}
function navigate(media: Media) {
  if (desktopBridge) { ++epoch; controller?.abort(); verified.value = null }
  emit('navigate', media)
}
watch([() => props.initialMedia.id, () => authIdentity()], () => { void verify() }, { immediate: true })
onBeforeUnmount(() => { ++epoch; controller?.abort() })
</script>
<template>
  <div>
    <MediaDetail v-if="verified" :key="desktopBridge ? verified.id : undefined" :initial-media="verified" :all-media="allMedia"
      :has-adjacent-media-page="hasAdjacentMediaPage" :load-adjacent-media-page="loadAdjacentMediaPage"
      @close="emit('close')" @updated="emit('updated', $event)" @navigate="navigate" @discarded="emit('discarded', $event)" />
    <Teleport to="body">
      <div v-if="!verified" class="fixed inset-0 z-[230] grid place-items-center bg-background/95" @keydown.esc="emit('close')">
        <div class="space-y-4 text-center">
          <EmptyState v-if="error" title="无法打开作品" :description="error" tone="warning"><UiButton @click="verify">重试</UiButton></EmptyState>
          <LoadingState v-else label="正在打开作品" description="正在验证登录与作品信息。" />
          <UiButton autofocus @click="emit('close')">取消</UiButton>
        </div>
      </div>
    </Teleport>
  </div>
</template>
