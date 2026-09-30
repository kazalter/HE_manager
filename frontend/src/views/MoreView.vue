<script setup lang="ts">
import { BarChart3, Book, ChevronRight, CopyMinus, Download, Palette, Settings, Sparkles, Tags, Users, LogOut } from 'lucide-vue-next'
import { authState, logout } from '../auth'
const links = [
  { to: '/downloads', label: '下载任务', hint: '查看服务器下载进度', icon: Download },
  { to: '/creators', label: '作者', hint: '浏览关注的创作者', icon: Book },
  { to: '/tags', label: '标签', hint: '按标签整理媒体', icon: Tags },
  { to: '/recommend', label: '漫画推荐', hint: '发现想读的作品', icon: Sparkles },
  { to: '/stats', label: '数据看板', hint: '查看媒体库概览', icon: BarChart3 },
  { to: '/bd2-spine', label: '角色鉴赏', hint: '浏览角色动画', icon: Palette },
  { to: '/settings', label: '设置', hint: '目录、同步与外观', icon: Settings },
]
const signOut = () => { if (window.confirm('确定退出当前账号吗？')) void logout() }
</script>
<template>
  <div class="he-more-page p-4 sm:p-8 max-w-3xl mx-auto">
    <header class="he-page-header mb-6"><p class="text-sm text-white/60 mb-1">HE Manager</p><h1 class="text-2xl font-bold text-white">更多</h1><p class="text-sm text-white/65 mt-2">{{ authState.user?.username }} · 个人媒体中心</p></header>
    <div class="rounded-2xl overflow-hidden border border-white/10 bg-white/[0.03] divide-y divide-white/10">
      <router-link v-for="link in links" :key="link.to" :to="link.to" class="flex items-center gap-4 p-4 min-h-20 active:bg-white/10 focus-visible:ring-2 focus-visible:ring-accent">
        <component :is="link.icon" :size="22" class="text-accent shrink-0" aria-hidden="true" /><span class="flex-1 min-w-0"><span class="block text-base font-semibold">{{ link.label }}</span><span class="block text-xs text-white/65 mt-1">{{ link.hint }}</span></span><ChevronRight :size="18" class="text-white/50" aria-hidden="true" />
      </router-link>
      <template v-if="authState.user?.is_admin">
        <router-link to="/dedup" class="flex items-center gap-4 p-4 min-h-16"><CopyMinus :size="22" class="text-accent" aria-hidden="true" /><span class="flex-1">重复媒体管理</span><ChevronRight :size="18" aria-hidden="true" /></router-link>
        <router-link to="/users" class="flex items-center gap-4 p-4 min-h-16"><Users :size="22" class="text-accent" aria-hidden="true" /><span class="flex-1">用户管理</span><ChevronRight :size="18" aria-hidden="true" /></router-link>
      </template>
    </div>
    <button type="button" class="mt-6 min-h-12 w-full rounded-xl border border-white/15 flex items-center justify-center gap-2 text-white/75" @click="signOut"><LogOut :size="18" aria-hidden="true" />退出登录</button>
  </div>
</template>
