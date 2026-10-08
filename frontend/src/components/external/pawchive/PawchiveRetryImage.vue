<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { withRetryParam } from '../../../utils/pawchiveApi'

defineOptions({ inheritAttrs: false })

// A transient proxy hiccup should not leave a cover blank until the list remounts.
const RETRY_DELAYS_MS = [1500, 4000]

const props = defineProps<{ src: string }>()
const emit = defineEmits<{ failed: [] }>()

const attempt = ref(0)
const waiting = ref(false)
const failed = ref(false)
let retryTimer: number | undefined

const currentSrc = computed(() => withRetryParam(props.src, attempt.value))

const reset = () => {
  window.clearTimeout(retryTimer)
  retryTimer = undefined
  attempt.value = 0
  waiting.value = false
  failed.value = false
}

const onError = () => {
  if (attempt.value >= RETRY_DELAYS_MS.length) {
    waiting.value = false
    failed.value = true
    emit('failed')
    return
  }
  waiting.value = true
  retryTimer = window.setTimeout(() => {
    retryTimer = undefined
    waiting.value = false
    attempt.value++
  }, RETRY_DELAYS_MS[attempt.value])
}

watch(() => props.src, reset)
onBeforeUnmount(() => window.clearTimeout(retryTimer))
</script>

<template>
  <img v-if="src && !failed" v-bind="$attrs" :src="currentSrc" :class="{ invisible: waiting }" @error="onError" />
  <slot v-else name="fallback" />
</template>
