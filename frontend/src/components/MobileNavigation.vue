<script setup lang="ts">
import { computed, onBeforeUnmount, reactive, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { Compass, Ellipsis, Library, Star } from 'lucide-vue-next'
const route = useRoute()
const router = useRouter()
const saved = reactive({ library: '/', favorites: '/?favorite=true', discover: '/external' })
try {
  const values = JSON.parse(sessionStorage.getItem('he_mobile_tabs') || '{}')
  for (const key of ['library', 'favorites', 'discover'] as const) {
    const value = values[key]
    if (typeof value === 'string' && /^\/(?:\?|$|type\/|external(?:\?|$))/.test(value)) saved[key] = value
  }
} catch { /* optional */ }
const section = computed(() => route.path === '/external' ? 'discover' : route.path === '/' || route.path.startsWith('/type/') ? route.query.favorite === 'true' ? 'favorites' : 'library' : 'more')
watch(() => route.fullPath, () => {
  const key = section.value
  if (key === 'more') return
  const query = new URLSearchParams()
  for (const [name, value] of Object.entries(route.query)) {
    if (name !== 'media' && typeof value === 'string') query.set(name, value)
  }
  saved[key] = route.path + (query.size ? '?' + query.toString() : '')
  try { sessionStorage.setItem('he_mobile_tabs', JSON.stringify(saved)) } catch { /* optional */ }
}, { immediate: true })
const items = computed(() => [
  { key: 'library', title: '媒体库', icon: Library, to: saved.library },
  { key: 'discover', title: '发现', icon: Compass, to: saved.discover },
  { key: 'favorites', title: '收藏', icon: Star, to: saved.favorites },
  { key: 'more', title: '更多', icon: Ellipsis, to: '/more' },
])
const surface = ref<HTMLElement | null>(null)
const dragPosition = ref<number | null>(null)
const activeIndex = computed(() => items.value.findIndex(item => item.key === section.value))
const lensPosition = computed(() => dragPosition.value ?? activeIndex.value)
const previewIndex = computed(() => Math.round(lensPosition.value))
let gesture: { id: number; x: number; y: number; left: number; lane: number; dragging: boolean } | null = null
let suppressClick = false
let clickTimer: number | undefined
const resetGesture = () => {
  const pointerId = gesture?.id
  gesture = null
  dragPosition.value = null
  if (pointerId !== undefined && surface.value?.hasPointerCapture?.(pointerId)) surface.value.releasePointerCapture(pointerId)
}
// Touch starts with implicit capture on the tapped icon or link. Transferring it to the
// surface emits a bubbled lostpointercapture from that child, not a cancellation.
const onLostPointerCapture = (event: PointerEvent) => {
  if (event.target === surface.value && gesture?.id === event.pointerId) resetGesture()
}
const onPointerDown = (event: PointerEvent) => {
  if (gesture || event.button !== 0 || event.isPrimary === false || !surface.value) return
  suppressClick = false
  window.clearTimeout(clickTimer)
  const box = surface.value.getBoundingClientRect()
  gesture = { id: event.pointerId, x: event.clientX, y: event.clientY, left: box.left + 5, lane: (box.width - 10) / 4, dragging: false }
}
const onPointerMove = (event: PointerEvent) => {
  if (!gesture || gesture.id !== event.pointerId) return
  const dx = Math.abs(event.clientX - gesture.x), dy = Math.abs(event.clientY - gesture.y)
  if (!gesture.dragging) {
    if (dy > 8 && dy > dx) { resetGesture(); return }
    if (dx < 8 || dx <= dy) return
    gesture.dragging = true
    surface.value?.setPointerCapture?.(event.pointerId)
  }
  event.preventDefault()
  dragPosition.value = Math.max(0, Math.min(3, (event.clientX - gesture.left) / gesture.lane - 0.5))
}
const onPointerUp = (event: PointerEvent) => {
  if (!gesture || gesture.id !== event.pointerId) return
  const target = gesture.dragging ? previewIndex.value : null
  if (gesture.dragging) {
    suppressClick = true
    clickTimer = window.setTimeout(() => { suppressClick = false }, 300)
  }
  resetGesture()
  if (target !== null && target !== activeIndex.value) void router.push(items.value[target]!.to)
}
const onClick = (event: MouseEvent) => {
  if (!suppressClick || event.detail === 0) return
  suppressClick = false
  event.preventDefault(); event.stopPropagation()
}
watch(() => route.fullPath, resetGesture)
onBeforeUnmount(() => { resetGesture(); window.clearTimeout(clickTimer) })
</script>
<template>
  <nav class="he-mobile-nav" aria-label="手机主导航">
    <div ref="surface" class="he-nav-surface" :class="{ 'is-dragging': dragPosition !== null }" :style="{ '--he-nav-index': lensPosition }" @pointerdown="onPointerDown" @pointermove="onPointerMove" @pointerup="onPointerUp" @pointercancel="resetGesture" @lostpointercapture="onLostPointerCapture" @click.capture="onClick" @dragstart.prevent>
      <div class="he-nav-lens" aria-hidden="true"></div>
      <router-link v-for="(item, index) in items" :key="item.key" :to="item.to" :aria-current="section === item.key ? 'page' : undefined" :class="{ active: section === item.key, 'is-preview': previewIndex === index }" draggable="false">
        <component :is="item.icon" :size="21" :stroke-width="section === item.key ? 2.2 : 1.9" aria-hidden="true" />
        <span>{{ item.title }}</span>
      </router-link>
    </div>
  </nav>
</template>
