<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import L2dStage from './components/L2dStage.vue'
import SkinTab from './components/tabs/SkinTab.vue'
import StateTab from './components/tabs/StateTab.vue'
import { MODELS, TRIGGER_LABELS, TRIGGER_ORDER } from './utils/models'

const query = new URLSearchParams(location.search)
const wallpaper = location.protocol === 'he:' && query.get('wallpaper') === '1' && window.parent === window
const requestedModel = wallpaper ? query.get('model') : ''
const activeId = ref(wallpaper ? (MODELS.find((model) => model.id === requestedModel)?.id ?? '') : (MODELS[0]?.id ?? ''))
const activeModel = computed(() => MODELS.find((m) => m.id === activeId.value))
const wallpaperPaused = ref(false)
watch(activeId, (id) => {
  if (!wallpaper && window.parent !== window) window.parent.postMessage({ type: 'l2d:model', id }, window.location.origin)
}, { immediate: true })
function onWallpaperActivity(event) {
  if (wallpaper && event.source === window && event.origin === location.origin && event.data?.type === 'he:wallpaper-activity') {
    wallpaperPaused.value = event.data.animate !== true
  }
}
function reportStage(success) { if (wallpaper) window.heWallpaper?.report(success) }
function reportPlayback(playing) { if (wallpaper) window.heWallpaper?.reportPlayback(playing) }

/** SkinTab 吃 { id, label }，模型名通过 label 字段适配，避免清单耦合视图。 */
const tabs = computed(() => MODELS.map((m) => ({ id: m.id, label: m.name })))

const stageRef = ref(null)
const layoutRef = ref(null)
const immersive = ref(false)
const fallbackFullscreen = ref(false)
const showControls = ref(false)
const showFullscreenHint = ref(false)
let hintTimer = null
let hideTimer = null
let holdTimer = null

function notifyParent(active) {
  if (window.parent !== window) window.parent.postMessage({ type: 'l2d:immersive', active }, window.location.origin)
}

function showEntryHint() {
  showFullscreenHint.value = true
  clearTimeout(hintTimer)
  hintTimer = setTimeout(() => { showFullscreenHint.value = false }, 4000)
}

async function enterFullscreen() {
  try {
    if (!layoutRef.value?.requestFullscreen) throw new Error('Fullscreen API unavailable')
    await layoutRef.value.requestFullscreen()
    fallbackFullscreen.value = false
  } catch {
    fallbackFullscreen.value = true
    notifyParent(true)
  }
  immersive.value = true
  showControls.value = false
  showEntryHint()
}

async function exitFullscreen() {
  if (document.fullscreenElement === layoutRef.value) await document.exitFullscreen()
  if (fallbackFullscreen.value) notifyParent(false)
  fallbackFullscreen.value = false
  immersive.value = false
  showControls.value = false
  showFullscreenHint.value = false
  clearTimeout(holdTimer)
  cancelHide()
}

function onFullscreenChange() {
  if (!document.fullscreenElement && immersive.value && !fallbackFullscreen.value) {
    immersive.value = false
    showControls.value = false
    showFullscreenHint.value = false
  }
}

function onKeydown(event) {
  if (event.key === 'Escape' && immersive.value && fallbackFullscreen.value) exitFullscreen()
}

function atEdge(event) {
  const rect = layoutRef.value.getBoundingClientRect()
  return event.clientX - rect.left <= 22 || rect.right - event.clientX <= 22 ||
    event.clientY - rect.top <= 22 || rect.bottom - event.clientY <= 22
}

function cancelHide() { clearTimeout(hideTimer); hideTimer = null }

function pointerMove(event) {
  if (!immersive.value || event.pointerType !== 'mouse') return
  if (atEdge(event)) {
    cancelHide()
    showControls.value = true
  } else if (event.target.closest('.side-tabs, .trigger-tabs, .camera-controls, .stage-toolbar, .debug-stack')) {
    cancelHide()
  } else if (showControls.value && !hideTimer) {
    hideTimer = setTimeout(() => { showControls.value = false; hideTimer = null }, 1500)
  }
}

function pointerDown(event) {
  if (!immersive.value || event.pointerType !== 'touch') return
  if (atEdge(event)) {
    clearTimeout(holdTimer)
    holdTimer = setTimeout(() => { showControls.value = true }, 650)
  } else if (event.target.closest('.canvas-host')) {
    showControls.value = false
  }
}

function pointerUp() { clearTimeout(holdTimer) }

onMounted(() => {
  if (wallpaper && !activeModel.value) window.heWallpaper?.report(false)
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('keydown', onKeydown)
  window.addEventListener('message', onWallpaperActivity)
})
onBeforeUnmount(() => {
  if (fallbackFullscreen.value) notifyParent(false)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('keydown', onKeydown)
  window.removeEventListener('message', onWallpaperActivity)
  clearTimeout(hintTimer)
  clearTimeout(hideTimer)
  clearTimeout(holdTimer)
})
/** 当前模型的可触发动作组（由舞台加载后上报）与最近一次触发项 */
const triggers = ref([])
const activeTrigger = ref('')
/**
 * 不进状态触发面板的动作组：idle 是自动循环的待机动作、effect 是常驻氛围层
 * （ambient.js 叠加）、touch_idle/touch_drag 只由舞台手势（点击/拖拽松手）
 * 触发；按 TRIGGER_ORDER 排列，未收录的排末尾。
 */
const NON_TRIGGERS = new Set(['idle', 'effect', 'touch_idle', 'touch_drag'])
const triggerItems = computed(() => {
  const rank = (id) => {
    const i = TRIGGER_ORDER.indexOf(id)
    return i === -1 ? TRIGGER_ORDER.length : i
  }
  return triggers.value
    .filter((id) => !NON_TRIGGERS.has(id))
    .map((id) => ({ id, label: TRIGGER_LABELS[id] ?? id }))
    .sort((a, b) => rank(a.id) - rank(b.id)) // Array.sort 稳定，同级保持声明顺序
})

function playTrigger(id) {
  activeTrigger.value = id
  stageRef.value?.play(id)
}
</script>

<template>
  <div ref="layoutRef" class="layout" :class="{ immersive }" @pointermove="pointerMove"
    @pointerdown="pointerDown" @pointerup="pointerUp" @pointercancel="pointerUp">
    <!-- 舞台永远占满容器，两侧栏作为蒙板浮在上面 -->
    <L2dStage v-if="activeModel" ref="stageRef" class="stage" :key="activeModel.id" :model-url="activeModel.url"
      :fill="0.8" :immersive="immersive" :paused="wallpaper && wallpaperPaused" :controls-visible="!wallpaper && (!immersive || showControls)" @stage-result="reportStage" @playback-state="reportPlayback" @motions="triggers = $event" @enter-fullscreen="enterFullscreen" />
    <SkinTab v-if="!wallpaper" v-show="!immersive || showControls" v-model="activeId" :tabs="tabs" title="皮肤列表" />
    <StateTab v-if="!wallpaper" v-show="!immersive || showControls" :items="triggerItems" :active="activeTrigger" title="状态触发" @select="playTrigger" />
    <template v-if="immersive">
      <p v-if="showFullscreenHint" class="fullscreen-hint">鼠标移到边缘显示界面；按 Esc 退出全屏</p>
    </template>
  </div>
</template>

<style scoped>
.layout {
  position: relative;
  width: 100%;
  height: 100%;
  overflow: hidden;
}

.stage {
  width: 100%;
  height: 100%;
}

.layout.immersive { background: #101014; }
.fullscreen-hint {
  position: absolute; z-index: 29; top: 22px; left: 50%; transform: translateX(-50%);
  color: white; background: #17171dcc; border-radius: 8px; padding: 8px 12px;
  max-width: calc(100% - 32px); text-align: center;
  font: 13px system-ui, sans-serif; pointer-events: none;
}
</style>
