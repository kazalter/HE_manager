<script setup>
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import L2dStage from './components/L2dStage.vue'
import SkinTab from './components/tabs/SkinTab.vue'
import StateTab from './components/tabs/StateTab.vue'
import { MODELS, TRIGGER_LABELS, TRIGGER_ORDER } from './utils/models'

const activeId = ref(MODELS[0]?.id ?? '')
const activeModel = computed(() => MODELS.find((m) => m.id === activeId.value))

/** SkinTab 吃 { id, label }，模型名通过 label 字段适配，避免清单耦合视图。 */
const tabs = computed(() => MODELS.map((m) => ({ id: m.id, label: m.name })))

const stageRef = ref(null)
const layoutRef = ref(null)
const immersive = ref(false)
const fallbackFullscreen = ref(false)
const showExit = ref(false)
const showFullscreenHint = ref(false)
let hintTimer = null
let exitTimer = null
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
  showExit.value = false
  showEntryHint()
}

async function exitFullscreen() {
  if (document.fullscreenElement === layoutRef.value) await document.exitFullscreen()
  if (fallbackFullscreen.value) notifyParent(false)
  fallbackFullscreen.value = false
  immersive.value = false
  showExit.value = false
  showFullscreenHint.value = false
  clearTimeout(holdTimer)
  clearTimeout(exitTimer)
}

function onFullscreenChange() {
  if (!document.fullscreenElement && immersive.value && !fallbackFullscreen.value) {
    immersive.value = false
    showExit.value = false
    showFullscreenHint.value = false
  }
}

function onKeydown(event) {
  if (event.key === 'Escape' && immersive.value && fallbackFullscreen.value) exitFullscreen()
}

function revealExit() {
  clearTimeout(exitTimer)
  showExit.value = true
  exitTimer = setTimeout(() => { showExit.value = false }, 4000)
}

function edgeDown(event) {
  if (event.pointerType !== 'touch') return
  clearTimeout(holdTimer)
  holdTimer = setTimeout(revealExit, 650)
}

function edgeUp() { clearTimeout(holdTimer) }

onMounted(() => {
  document.addEventListener('fullscreenchange', onFullscreenChange)
  document.addEventListener('keydown', onKeydown)
})
onBeforeUnmount(() => {
  if (fallbackFullscreen.value) notifyParent(false)
  document.removeEventListener('fullscreenchange', onFullscreenChange)
  document.removeEventListener('keydown', onKeydown)
  clearTimeout(hintTimer)
  clearTimeout(exitTimer)
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
  <div ref="layoutRef" class="layout" :class="{ immersive }">
    <!-- 舞台永远占满容器，两侧栏作为蒙板浮在上面 -->
    <L2dStage v-if="activeModel" ref="stageRef" class="stage" :key="activeModel.id" :model-url="activeModel.url"
      :fill="0.8" :immersive="immersive" @motions="triggers = $event" @enter-fullscreen="enterFullscreen" />
    <SkinTab v-if="!immersive" v-model="activeId" :tabs="tabs" title="皮肤列表" />
    <StateTab v-if="!immersive" :items="triggerItems" :active="activeTrigger" title="状态触发" @select="playTrigger" />
    <template v-if="immersive">
      <div class="fullscreen-edge" @pointerenter="(e) => e.pointerType === 'mouse' && revealExit()"
        @pointerdown="edgeDown" @pointerup="edgeUp" @pointercancel="edgeUp" @pointerleave="edgeUp" />
      <button v-if="showExit" class="fullscreen-exit" type="button" @pointerenter="revealExit" @click="exitFullscreen">退出全屏</button>
      <p v-if="showFullscreenHint" class="fullscreen-hint">按 Esc 退出；触屏长按顶部边缘显示退出按钮</p>
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
.fullscreen-edge { position: absolute; z-index: 30; top: 0; left: 0; right: 0; height: 22px; touch-action: none; }
.fullscreen-exit {
  position: absolute; z-index: 31; top: 12px; left: 50%; transform: translateX(-50%);
  border: 1px solid #ffffff55; border-radius: 9px; padding: 9px 15px;
  background: #17171de8; color: white; font: 14px system-ui, sans-serif; cursor: pointer;
}
.fullscreen-hint {
  position: absolute; z-index: 29; top: 22px; left: 50%; transform: translateX(-50%);
  color: white; background: #17171dcc; border-radius: 8px; padding: 8px 12px;
  max-width: calc(100% - 32px); text-align: center;
  font: 13px system-ui, sans-serif; pointer-events: none;
}
</style>
