<script setup lang="ts">
import { computed } from 'vue'
import { BarChart3, Book, ChevronRight, CopyMinus, Download, LogOut, Palette, Settings, Smartphone, Sparkles, Tags, Users } from 'lucide-vue-next'
import { authState, logout } from '../auth'
import { PageHeader, SectionHeader, UiButton, UiCard } from '../components/ui'

const standalone = window.matchMedia('(display-mode: standalone)').matches || (navigator as Navigator & { standalone?: boolean }).standalone === true
const links = [
  { to: '/downloads', label: '下载任务', hint: '查看服务器下载进度', icon: Download, group: 'tools' },
  { to: '/creators', label: '作者', hint: '浏览关注的创作者', icon: Book, group: 'library' },
  { to: '/tags', label: '标签', hint: '按标签整理媒体', icon: Tags, group: 'library' },
  { to: '/recommend', label: '漫画推荐', hint: '发现想读的作品', icon: Sparkles, group: 'library' },
  { to: '/stats', label: '数据看板', hint: '查看媒体库概览', icon: BarChart3, group: 'tools' },
  { to: '/bd2-spine', label: '角色鉴赏', hint: '浏览角色动画', icon: Palette, group: 'library' },
  { to: '/settings', label: '设置', hint: '目录、同步与外观', icon: Settings, group: 'tools' },
]
const adminLinks = [
  { to: '/dedup', label: '重复媒体管理', hint: '检测并合并重复内容', icon: CopyMinus, group: 'admin' },
  { to: '/users', label: '用户管理', hint: '管理登录账号', icon: Users, group: 'admin' },
]
const groups = computed(() => [
  { key: 'library', title: '浏览', items: links.filter(link => link.group === 'library') },
  { key: 'tools', title: '工具', items: links.filter(link => link.group === 'tools') },
  ...(authState.user?.is_admin ? [{ key: 'admin', title: '管理', items: adminLinks }] : []),
])
const userInitial = computed(() => (authState.user?.username?.trim()[0] || '?').toUpperCase())
const signOut = () => { if (window.confirm('确定退出当前账号吗？')) void logout() }
</script>

<template>
  <div class="he-more-page min-h-full">
    <PageHeader title="更多" description="HE Manager · 个人媒体中心" />

    <div class="page-gutter pb-12">
      <div class="page-container">
        <div class="max-w-[960px] space-y-8">
          <UiCard padding="sm" class="flex items-center gap-3">
            <div class="grid size-11 shrink-0 place-items-center rounded-full bg-surface-3 text-body font-medium text-muted" aria-hidden="true">{{ userInitial }}</div>
            <div class="min-w-0 flex-1">
              <p class="truncate text-body font-medium text-ink">{{ authState.user?.username }}</p>
              <p class="mt-0.5 text-meta text-subtle">{{ authState.user?.is_admin ? '管理员' : '普通用户' }}</p>
            </div>
            <UiButton variant="ghost" size="sm" class="hover:!bg-danger/12 hover:!text-danger" @click="signOut">
              <template #icon><LogOut :size="14" /></template>
              退出登录
            </UiButton>
          </UiCard>

          <section v-for="group in groups" :key="group.key">
            <SectionHeader :title="group.title" as="h2" />
            <UiCard padding="none" class="divide-y divide-line overflow-hidden">
              <router-link
                v-for="link in group.items"
                :key="link.to"
                :to="link.to"
                class="flex min-h-16 items-center gap-3 px-4 py-3 transition-colors duration-150 hover:bg-surface-2 active:bg-surface-2 focus-ring-inset"
              >
                <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted" aria-hidden="true">
                  <component :is="link.icon" :size="18" />
                </span>
                <span class="min-w-0 flex-1">
                  <span class="block truncate text-body font-medium text-ink">{{ link.label }}</span>
                  <span class="mt-0.5 block truncate text-meta text-subtle">{{ link.hint }}</span>
                </span>
                <ChevronRight :size="18" class="shrink-0 text-faint" aria-hidden="true" />
              </router-link>
            </UiCard>
          </section>

          <details v-if="!standalone" class="group rounded-2xl border border-line bg-surface">
            <summary class="flex min-h-14 cursor-pointer list-none items-center gap-3 rounded-2xl px-4 py-3 focus-ring-inset [&::-webkit-details-marker]:hidden">
              <span class="grid size-9 shrink-0 place-items-center rounded-lg bg-surface-2 text-muted" aria-hidden="true"><Smartphone :size="18" /></span>
              <span class="min-w-0 flex-1">
                <span class="block text-body font-medium text-ink">添加到 iPhone 主屏幕</span>
                <span class="mt-0.5 block text-meta text-subtle">像 App 一样全屏打开</span>
              </span>
              <ChevronRight :size="18" class="shrink-0 text-faint transition-transform duration-150 group-open:rotate-90" aria-hidden="true" />
            </summary>
            <div class="border-t border-line px-4 pt-3 pb-4">
              <ol class="list-decimal space-y-1.5 pl-5 text-body leading-relaxed text-muted"><li>用 Safari 打开当前 HE Manager 地址。</li><li>点击「分享」，选择「添加到主屏幕」。</li><li>若有「作为 Web App 打开」选项，保持开启，然后点「添加」。</li></ol>
              <p class="mt-3 text-meta text-subtle">从桌面图标打开即可使用，无需开发者模式。手机需要能连接到服务器；首次打开可能需要重新登录。</p>
            </div>
          </details>
        </div>
      </div>
    </div>
  </div>
</template>
