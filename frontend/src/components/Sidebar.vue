<script setup lang="ts">
import { computed, ref } from 'vue'
import { useRoute } from 'vue-router'
import {
  BarChart3,
  Book,
  Box,
  ChevronLeft,
  ChevronRight,
  CopyMinus,
  Film,
  Globe2,
  Headphones,
  Home,
  Image as ImageIcon,
  LogOut,
  Palette,
  RefreshCw,
  Settings as SettingsIcon,
  Sparkles,
  Star,
  Tags,
  Users,
} from 'lucide-vue-next'
import type { User } from '../types'

const props = withDefaults(defineProps<{
  collapsed: boolean
  isCompact?: boolean
  user: User | null
}>(), {
  isCompact: false,
})

const emit = defineEmits<{
  'update:collapsed': [value: boolean]
  logout: []
}>()
const route = useRoute()

const isHomeActive = computed(() => route.path === '/' && route.query.favorite !== 'true')
const isFavoriteActive = computed(() => route.path === '/' && route.query.favorite === 'true')

const isRefreshing = ref(false)
const refreshApp = () => {
  if (isRefreshing.value) return
  isRefreshing.value = true
  setTimeout(() => {
    window.location.reload()
  }, 400)
}

const toggle = () => {
  emit('update:collapsed', !props.collapsed)
}

const handleLogout = () => {
  if (window.confirm('确定要退出登录当前账号吗？')) {
    emit('logout')
  }
}
</script>

<template>
  <aside
    :class="[
      isCompact
        ? (collapsed ? 'w-64 -translate-x-full opacity-0 pointer-events-none fixed left-0 top-0 z-50 h-full my-0 ml-0 rounded-none border-r border-white/10' : 'w-64 translate-x-0 opacity-100 fixed left-0 top-0 z-50 h-full my-0 ml-0 rounded-none border-r border-white/10 shadow-2xl')
        : (collapsed ? 'w-[4.5rem] p-2.5' : 'w-64 p-4'),
      !isCompact ? 'h-[calc(100vh-2rem)] my-4 ml-4 rounded-2xl border border-white/8 shadow-[0_15px_35px_-10px_rgba(0,0,0,0.6)]' : ''
    ]"
    class="bg-sidebar/85 backdrop-blur-2xl flex flex-col transition-all duration-300 ease-in-out relative group z-40 select-none"
  >
    <!-- Toggle Collapse Floating Button (Desktop) -->
    <button
      v-if="!isCompact"
      @click="toggle"
      class="absolute -right-3 top-9 w-6 h-6 rounded-full bg-accent border border-white/20 flex items-center justify-center text-white shadow-md shadow-accent/25 hover:scale-110 active:scale-95 transition-all z-50 opacity-0 group-hover:opacity-100 cursor-pointer"
      :title="collapsed ? '展开侧边栏' : '收起侧边栏'"
    >
      <ChevronLeft v-if="!collapsed" :size="13" />
      <ChevronRight v-else :size="13" />
    </button>

    <!-- App Brand & Title Header -->
    <div
      class="mb-4 flex items-center overflow-hidden whitespace-nowrap transition-all"
      :class="collapsed && !isCompact ? 'justify-center px-0 py-1' : 'justify-between px-2 py-1 gap-3'"
    >
      <div class="flex items-center gap-3 min-w-0">
        <div class="shrink-0 w-9 h-9 rounded-xl bg-gradient-to-tr from-accent to-indigo-500 shadow-md shadow-accent/25 flex items-center justify-center overflow-hidden">
          <span class="text-sm font-black text-white tracking-wide">HE</span>
        </div>

        <div v-if="!collapsed || isCompact" class="min-w-0">
          <h1 class="text-lg font-black tracking-tight text-white truncate">
            HE Manager
          </h1>
          <p class="text-xs text-white/45 font-medium -mt-0.5">个人媒体中心</p>
        </div>
      </div>

      <button
        v-if="!collapsed || isCompact"
        @click="refreshApp"
        class="text-white/35 hover:text-accent hover:bg-accent/15 p-1.5 rounded-lg transition-all shrink-0 flex items-center justify-center cursor-pointer"
        title="刷新页面"
      >
        <RefreshCw :size="16" :stroke-width="2.2" :class="{ 'animate-spin': isRefreshing }" class="hover:rotate-180 transition-transform duration-500" />
      </button>
    </div>

    <!-- Navigation Scroll Area -->
    <nav class="flex-1 space-y-1 overflow-x-hidden overflow-y-auto custom-scrollbar pr-0.5">
      <!-- Section 1: 媒体库 -->
      <div class="space-y-1">
        <div v-if="!collapsed || isCompact" class="px-3 pt-2 pb-1 text-xs font-bold uppercase tracking-wider text-white/40">
          媒体库
        </div>

        <router-link
          to="/"
          :class="[
            collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5',
            isHomeActive ? 'bg-accent/20 text-white border-accent/40 font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]' : 'text-white/60 hover:text-white hover:bg-white/6 border-transparent'
          ]"
          class="flex items-center rounded-xl border transition-all duration-200 group relative"
          title="全部媒体"
        >
          <Home :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">全部媒体</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            全部媒体
          </div>
        </router-link>

        <router-link
          to="/type/video"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="视频"
        >
          <Film :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">视频</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            视频
          </div>
        </router-link>

        <router-link
          to="/type/manga"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="漫画"
        >
          <Book :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">漫画</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            漫画
          </div>
        </router-link>

        <router-link
          to="/type/image"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="杂图"
        >
          <ImageIcon :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">杂图</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            杂图
          </div>
        </router-link>

        <router-link
          to="/type/audio"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="音频"
        >
          <Headphones :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">音频</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            音频
          </div>
        </router-link>

        <router-link
          :to="{ path: '/', query: { favorite: 'true' } }"
          :class="[
            collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5',
            isFavoriteActive ? 'bg-accent/20 text-white border-accent/40 font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]' : 'text-white/60 hover:text-white hover:bg-white/6 border-transparent'
          ]"
          class="flex items-center rounded-xl border transition-all duration-200 group relative"
          title="收藏"
        >
          <Star :size="20" class="group-hover:scale-110 transition-transform shrink-0 text-amber-300" :fill="isFavoriteActive ? 'currentColor' : 'none'" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">收藏</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            收藏
          </div>
        </router-link>
      </div>

      <!-- Section Divider -->
      <div class="border-t border-white/6 my-2 mx-1"></div>

      <!-- Section 2: 发现与整理 -->
      <div class="space-y-1">
        <div v-if="!collapsed || isCompact" class="px-3 pt-1 pb-1 text-xs font-bold uppercase tracking-wider text-white/40">
          发现与整理
        </div>

        <router-link
          v-if="user?.is_admin"
          to="/external"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="外部收藏"
        >
          <Globe2 :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">外部收藏</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            外部收藏
          </div>
        </router-link>

        <router-link
          to="/recommend"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="AI 推荐"
        >
          <Sparkles :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">AI 推荐</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            AI 推荐
          </div>
        </router-link>

        <router-link
          to="/creators"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="创作者"
        >
          <Palette :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">创作者</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            创作者
          </div>
        </router-link>

        <router-link
          to="/tags"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="标签管理"
        >
          <Tags :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">标签管理</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            标签管理
          </div>
        </router-link>
      </div>

      <!-- Section Divider -->
      <div class="border-t border-white/6 my-2 mx-1"></div>

      <!-- Section 3: 系统与工具 -->
      <div class="space-y-1">
        <div v-if="!collapsed || isCompact" class="px-3 pt-1 pb-1 text-xs font-bold uppercase tracking-wider text-white/40">
          系统与工具
        </div>

        <router-link
          to="/bd2-spine"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="BD2 动态"
        >
          <Box :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">BD2 动态</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            BD2 动态
          </div>
        </router-link>

        <router-link
          to="/stats"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="统计看板"
        >
          <BarChart3 :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">统计看板</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            统计看板
          </div>
        </router-link>

        <router-link
          v-if="user?.is_admin"
          to="/dedup"
          :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
          class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
          active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
          title="重复管理"
        >
          <CopyMinus :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
          <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">重复管理</span>
          <div
            v-if="collapsed && !isCompact"
            class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
          >
            重复管理
          </div>
        </router-link>
      </div>
    </nav>

    <!-- Bottom Actions Area -->
    <div class="mt-auto space-y-1 pt-3 border-t border-white/8 overflow-hidden">
      <router-link
        v-if="user?.is_admin"
        to="/settings"
        :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
        class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
        active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
        title="设置"
      >
        <SettingsIcon :size="20" class="group-hover:rotate-45 transition-transform shrink-0" />
        <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">设置</span>
        <div
          v-if="collapsed && !isCompact"
          class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
        >
          设置
        </div>
      </router-link>

      <router-link
        v-if="user?.is_admin"
        to="/users"
        :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
        class="flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/60 hover:text-white hover:bg-white/6"
        active-class="!bg-accent/20 !text-white !border-accent/40 !font-bold shadow-[inset_0_1px_0_0_rgba(255,255,255,0.1)]"
        title="用户管理"
      >
        <Users :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
        <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">用户管理</span>
        <div
          v-if="collapsed && !isCompact"
          class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-white shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
        >
          用户管理
        </div>
      </router-link>

      <button
        type="button"
        @click="handleLogout"
        :class="collapsed && !isCompact ? 'w-full justify-center p-2.5' : 'px-3 py-2.5 gap-3.5'"
        class="w-full flex items-center rounded-xl border border-transparent transition-all duration-200 group relative text-white/55 hover:text-red-300 hover:bg-red-500/10 cursor-pointer text-left"
        title="退出登录"
      >
        <LogOut :size="20" class="group-hover:scale-110 transition-transform shrink-0" />
        <span v-if="!collapsed || isCompact" class="font-medium text-sm whitespace-nowrap overflow-hidden">退出登录</span>
        <div
          v-if="collapsed && !isCompact"
          class="pointer-events-none absolute left-[calc(100%+0.65rem)] top-1/2 -translate-y-1/2 px-2.5 py-1.5 rounded-xl bg-sidebar/95 backdrop-blur-xl border border-white/12 text-xs font-bold text-red-200 shadow-xl z-50 whitespace-nowrap opacity-0 -translate-x-1 group-hover:opacity-100 group-hover:translate-x-0 transition-all duration-200"
        >
          退出登录
        </div>
      </button>
    </div>
  </aside>
</template>
