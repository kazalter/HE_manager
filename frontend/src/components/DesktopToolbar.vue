<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { Monitor, Server, Settings2 } from 'lucide-vue-next'
import { desktopBridge, desktopState, setDesktopPreferences, type ImageEnhancement, type VideoEnhancement } from '../desktop'
import { controlClass, fieldLabelClass, UiButton, UiModal } from './ui'
import ColorModeSelect from './ColorModeSelect.vue'
const open = ref(false), server = ref(''), error = ref(''), busy = ref(false)
onMounted(() => { server.value = desktopState.server || 'http://192.168.0.101:8011'; open.value = !desktopState.server })
const changeServer = async () => {
 busy.value = true; error.value = ''
 try {
  await desktopBridge!.connect(server.value)
  localStorage.removeItem('he_manager_token')
  sessionStorage.clear()
  window.location.reload()
 } catch (e: any) { error.value = e.message } finally { busy.value = false }
}
const choose = async (kind: 'mpv' | 'image') => {
 error.value = ''
 try { Object.assign(desktopState, await desktopBridge!.chooseEngine(kind)) } catch (e: any) { error.value = e.message }
}
const preferences = async (videoMode: VideoEnhancement, imageMode: ImageEnhancement) => {
 error.value = ''
 try { await setDesktopPreferences(videoMode, imageMode) } catch (e: any) { error.value = e.message }
}
</script>
<template>
 <header class="he-desktop-toolbar flex h-11 items-center gap-3 border-b border-line bg-sidebar px-4 text-meta text-muted">
  <Monitor :size="16" aria-hidden="true" /><span class="font-medium text-ink">HE Manager 桌面版</span>
  <span class="min-w-0 flex-1 truncate">{{ desktopState.server || '尚未连接服务器' }}</span>
  <button type="button" class="flex min-h-9 items-center gap-2 rounded-lg px-3 hover:bg-surface-2 focus-ring" @click="open = true"><Settings2 :size="16" />连接与超分</button>
 </header>
 <UiModal v-model:open="open" title="桌面设置" @close="open = false">
  <div class="space-y-6">
   <section class="space-y-2" aria-labelledby="desktop-appearance-title">
    <h3 id="desktop-appearance-title" :class="fieldLabelClass">外观</h3>
    <ColorModeSelect />
    <p class="text-meta text-subtle">外观立即应用到整个客户端；跟随系统会自动切换白天和黑夜模式。</p>
   </section>
   <form class="space-y-2" @submit.prevent="changeServer">
    <label class="block"><span :class="fieldLabelClass">HE Manager 服务器地址</span><input v-model="server" :class="controlClass()" placeholder="http://192.168.0.101:8011" autocomplete="url" /></label>
    <p class="text-meta text-subtle">使用网页端访问地址；切换服务器后需要重新登录。</p>
    <UiButton type="submit" :loading="busy"><template #icon><Server :size="16" /></template>连接并保存</UiButton>
   </form>
   <section class="space-y-2">
    <label class="block"><span :class="fieldLabelClass">动漫视频增强</span><select :value="desktopState.videoMode" :class="controlClass()" @change="preferences(($event.target as HTMLSelectElement).value as VideoEnhancement, desktopState.imageMode)"><option value="off">原画／普通视频</option><option value="efficiency">Anime4K · 效率档</option><option value="quality">Anime4K · 质量档</option></select></label>
    <p class="text-meta text-subtle">在本机播放器窗口实时处理；M1 Pro 建议先用效率档。高分辨率源若掉帧可关闭增强。</p>
   </section>
   <section class="space-y-2">
    <label class="block"><span :class="fieldLabelClass">图片与漫画增强</span><select :value="desktopState.imageMode" :class="controlClass()" @change="preferences(desktopState.videoMode, ($event.target as HTMLSelectElement).value as ImageEnhancement)"><option value="off">显示原图</option><option value="anime">动漫／漫画 · 2×</option><option value="photo">普通图片 · 4×</option></select></label>
    <p class="text-meta text-subtle">仅增强当前可见的静态 JPG、PNG，处理时继续显示原图；缓存最多约 1GB，原文件保持不变。</p>
   </section>
   <section class="space-y-3 border-t border-line pt-4">
    <p class="text-meta text-muted">{{ desktopState.platform }} · {{ desktopState.arch }} · v{{ desktopState.version }}</p>
    <div class="flex items-center justify-between gap-3"><span class="text-body">mpv：{{ desktopState.mpv ? '已就绪' : '未找到' }}</span><UiButton size="sm" @click="choose('mpv')">选择引擎</UiButton></div>
    <div class="flex items-center justify-between gap-3"><span class="text-body">图片超分：{{ desktopState.image ? '已就绪' : '未找到' }}</span><UiButton size="sm" @click="choose('image')">选择引擎</UiButton></div>
   </section>
   <p v-if="error" role="alert" class="text-body text-danger">{{ error }}</p>
  </div>
 </UiModal>
</template>
<style>
.he-desktop .he-app-shell { height: calc(100dvh - 44px); }
.he-desktop .he-auth-view { min-height: calc(100dvh - 44px); }
</style>
