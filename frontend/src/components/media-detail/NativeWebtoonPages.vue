<script setup lang="ts">
import { nextTick, onBeforeUnmount, onMounted, ref, watch } from 'vue'

export interface NativeWebtoonPage { url: string; width?: number; height?: number; alt: string }
const props = defineProps<{ pages: NativeWebtoonPage[]; currentPage: number }>()
const emit = defineEmits<{ content: [element: HTMLDivElement | null] }>()
const root = ref<HTMLDivElement | null>(null)
// WNACG's vertical reader: stable slots, two downloads, current/+20/-3 priority.
// The downloaded Image itself is displayed. Keep loaded nodes; let the browser
// manage decoded surfaces rather than rebuilding images through a bitmap LRU.
const AHEAD = 20, BEHIND = 3, TIMEOUT = 60_000, PLACEHOLDER_MIN = 300
type Entry = { state: 'queued' | 'loading' | 'loaded' | 'failed'; since: number;
  image?: HTMLImageElement; timer?: number; swapTimer?: number }
const entries = new Map<number, Entry>()
const knownSizes = new Map<number, [number, number]>()
let current = props.currentPage, inflight = 0, disposed = false, resizeTimer = 0
const slotAt = (index: number) => root.value?.children[index] as HTMLElement | undefined
function slotHeight(index: number) {
  const page = props.pages[index]!, size = knownSizes.get(index)
  const width = size?.[0] || page.width, height = size?.[1] || page.height
  const column = root.value?.clientWidth || window.innerWidth
  return width && height ? Math.max(50, Math.round(Math.min(width, column) * height / width)) : Math.round(column * 1.4)
}
function reserve(index: number) { const slot = slotAt(index); if (slot) slot.style.minHeight = `${slotHeight(index)}px` }
function paint(index: number, entry: Entry) {
  const slot = slotAt(index)
  if (!slot) return
  reserve(index)
  slot.replaceChildren()
  slot.dataset.state = entry.state
  slot.setAttribute('aria-busy', String(entry.state !== 'failed'))
  const placeholder = document.createElement('div')
  placeholder.className = 'he-native-placeholder'
  const label = document.createElement('span')
  label.textContent = entry.state === 'failed' ? '图片加载失败' : `第 ${index + 1} / ${props.pages.length} 页 · ${entry.state === 'loading' ? '加载中…' : '排队中…'}`
  placeholder.append(label)
  if (entry.state === 'failed') {
    placeholder.setAttribute('role', 'status')
    const retry = document.createElement('button')
    retry.type = 'button'; retry.textContent = '重新加载'
    retry.onclick = event => { event.stopPropagation(); entries.delete(index); warm(current) }
    placeholder.append(retry)
  }
  slot.append(placeholder)
}
function start(index: number, entry: Entry) {
  entry.state = 'loading'; inflight++; paint(index, entry)
  const image = new Image()
  entry.image = image
  let done = false
  const finish = () => {
    if (done || disposed || entries.get(index) !== entry) return false
    done = true; clearTimeout(entry.timer); image.onload = image.onerror = null; inflight--
    return true
  }
  const fail = () => {
    if (!finish()) return
    image.removeAttribute('src'); entry.image = undefined; entry.state = 'failed'
    paint(index, entry); pump()
  }
  image.onerror = fail
  entry.timer = window.setTimeout(fail, TIMEOUT)
  image.onload = () => {
    if (!finish()) return
    entry.state = 'loaded'
    if (image.naturalWidth && image.naturalHeight) knownSizes.set(index, [image.naturalWidth, image.naturalHeight])
    const swap = () => {
      if (disposed || entries.get(index) !== entry) return
      const slot = slotAt(index)
      if (!slot) return
      const y = window.scrollY, above = slot.getBoundingClientRect().top < 0, oldHeight = slot.offsetHeight
      image.alt = props.pages[index]!.alt
      image.className = 'he-native-page-image'
      slot.replaceChildren(image); slot.style.minHeight = '0px'
      slot.dataset.state = 'loaded'; slot.setAttribute('aria-busy', 'false')
      const delta = slot.offsetHeight - oldHeight
      if (above && Math.abs(delta) > 1) window.scrollTo(0, Math.max(0, y + delta))
    }
    const wait = PLACEHOLDER_MIN - (Date.now() - entry.since)
    if (wait > 0) entry.swapTimer = window.setTimeout(swap, wait)
    else swap()
    pump()
  }
  image.src = props.pages[index]!.url
}
function order() {
  const indices: number[] = []
  for (let distance = 0; distance <= AHEAD; distance++) {
    if (current + distance < props.pages.length) indices.push(current + distance)
    if (distance > 0 && distance <= BEHIND && current - distance >= 0) indices.push(current - distance)
  }
  return indices
}
function pump() {
  if (disposed || !root.value) return
  for (const [index, entry] of entries) {
    if (Math.abs(index - current) > AHEAD + 4 && entry.state !== 'loaded' && entry.state !== 'loading') {
      slotAt(index)?.replaceChildren(); reserve(index); entries.delete(index)
    }
  }
  const indices = order()
  for (const index of indices) if (!entries.has(index)) {
    const entry: Entry = { state: 'queued', since: Date.now() }
    entries.set(index, entry); paint(index, entry)
  }
  for (const index of indices) {
    if (inflight >= 2) break
    const entry = entries.get(index)!
    if (entry.state === 'queued') start(index, entry)
  }
}
function warm(page: number) { current = Math.max(0, Math.min(page, props.pages.length - 1)); pump() }
function clear() {
  for (const entry of entries.values()) {
    clearTimeout(entry.timer); clearTimeout(entry.swapTimer)
    if (entry.image) { entry.image.onload = entry.image.onerror = null; entry.image.removeAttribute('src') }
  }
  entries.clear(); knownSizes.clear(); inflight = 0
}
function resizeSlots() { props.pages.forEach((_, index) => { if (entries.get(index)?.state !== 'loaded') reserve(index) }) }
function onResize() { clearTimeout(resizeTimer); resizeTimer = window.setTimeout(() => { resizeSlots(); pump() }, 200) }
watch(() => props.pages.map(page => page.url).join('\n'), async () => {
  clear(); await nextTick()
  if (disposed) return
  root.value?.querySelectorAll('.he-reader-page').forEach(slot => slot.replaceChildren())
  resizeSlots(); warm(props.currentPage)
})
watch(() => props.pages.map(page => `${page.width}:${page.height}`).join(','), resizeSlots, { flush: 'post' })
watch(() => props.currentPage, warm)
onMounted(() => { emit('content', root.value); resizeSlots(); warm(props.currentPage); window.addEventListener('resize', onResize, { passive: true }) })
onBeforeUnmount(() => { disposed = true; clear(); clearTimeout(resizeTimer); window.removeEventListener('resize', onResize); emit('content', null) })
defineExpose({ warm })
</script>

<template>
  <!-- No touch/pointer/gesture listeners and no nested scrolling surface. -->
  <div ref="root" class="he-webtoon-content he-native-pages">
    <div v-for="(page, index) in pages" :key="page.url" :id="`webtoon-page-${index}`"
      :data-page="index" class="he-reader-page he-native-page" :aria-label="page.alt" />
  </div>
</template>

<style>
.he-native-pages { display: flex; flex-direction: column; align-items: center; width: 100%; min-height: 100vh; }
.he-native-page { display: flex; justify-content: center; position: relative; width: 100%; overflow-anchor: none; }
.he-native-page-image { display: block; width: auto; height: auto; max-width: 100%; align-self: flex-start; pointer-events: auto; }
.he-native-placeholder { position: absolute; inset: 0; display: flex; flex-direction: column; align-items: center; justify-content: center; gap: 12px; background: #18181b; color: #a1a1aa; font-size: 14px; }
.he-native-placeholder button { min-height: 44px; padding: 8px 20px; border-radius: 999px; background: #3f3f46; color: white; }
</style>
