import { createRouter, createWebHashHistory, type RouteLocationNormalizedLoaded } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const TYPE_TITLES: Record<string, string> = {
  video: '视频',
  manga: '漫画',
  image: '杂图',
  audio: '音频',
}

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    { path: '/discarded', name: 'discarded', meta: { title: '丢弃记录' }, component: () => import('../views/DiscardedView.vue') },
    { path: '/assistant', name: 'assistant', meta: { title: '媒体库管家' }, component: () => import('../views/AssistantView.vue') },
    { path: '/more', name: 'more', meta: { title: '更多' }, component: () => import('../views/MoreView.vue') },
    { path: '/downloads', name: 'downloads', meta: { title: '下载任务' }, component: () => import('../views/DownloadsView.vue') },
    {
      path: '/',
      name: 'home',
      meta: { title: '全部媒体' },
      component: HomeView,
    },
    {
      path: '/type/:mediaType',
      name: 'type-filter',
      meta: { title: '媒体分类' },
      component: HomeView,
      props: true,
    },
    {
      path: '/settings',
      name: 'settings',
      meta: { title: '设置' },
      component: () => import('../views/SettingsView.vue'),
    },
    {
      path: '/external',
      name: 'external-favorites',
      meta: { title: '外部收藏' },
      component: () => import('../views/ExternalFavoritesView.vue'),
    },
    {
      path: '/external/pawchive',
      name: 'pawchive',
      redirect: to => ({ name: 'external-favorites', query: { ...to.query, source: 'pawchive' } }),
    },
    {
      path: '/dedup',
      name: 'dedup',
      meta: { title: '重复管理' },
      component: () => import('../views/DedupView.vue'),
    },
    {
      path: '/users',
      name: 'users',
      meta: { title: '用户管理' },
      component: () => import('../views/UsersView.vue'),
    },
    {
      // Dashboard stats: chart-heavy overview, distribution, activity, attention.
      path: '/stats',
      name: 'stats',
      meta: { title: '统计看板' },
      component: () => import('../views/StatsView.vue'),
    },
    {
      // Unified creators list (X authors + manga artists).
      path: '/creators',
      name: 'creators',
      meta: { title: '创作者' },
      component: () => import('../views/CreatorsView.vue'),
    },
    {
      // Creator detail (same view, branches on route.params.screenName).
      path: '/creators/:screenName',
      name: 'creator-detail',
      meta: { title: '创作者详情' },
      component: () => import('../views/CreatorsView.vue'),
      props: true,
    },
    {
      path: '/tags',
      name: 'tags',
      meta: { title: '标签管理' },
      component: () => import('../views/TagsView.vue'),
    },
    {
      path: '/recommend',
      redirect: '/assistant',
    },
    {
      path: '/bd2-spine',
      name: 'bd2-spine',
      meta: { title: 'BD2 动态' },
      component: () => import('../views/Bd2SpineView.vue'),
    },
    {
      path: '/bd2-spine/embed',
      name: 'bd2-spine-embed',
      meta: { title: 'BD2 动态嵌入' },
      component: () => import('../views/EmbedSpineView.vue'),
    },
    { path: '/live2d', name: 'live2d', meta: { title: '碧蓝航线' }, component: () => import('../views/Live2dView.vue') },
    {
      path: '/:pathMatch(.*)*',
      redirect: '/',
    },
  ],
})

export const resolveRouteTitle = (to: RouteLocationNormalizedLoaded): string => {
  if (to.name === 'type-filter') {
    const mediaType = typeof to.params.mediaType === 'string' ? to.params.mediaType : ''
    return TYPE_TITLES[mediaType] || '媒体分类'
  }
  if (to.name === 'creator-detail' && typeof to.params.screenName === 'string' && to.params.screenName) {
    return `${to.params.screenName} · 创作者`
  }
  if (to.name === 'home' && to.query.favorite === 'true') {
    return '我的收藏'
  }
  return typeof to.meta.title === 'string' ? to.meta.title : '媒体中心'
}

router.afterEach(to => {
  if (typeof document !== 'undefined') {
    document.title = `${resolveRouteTitle(to)} | HE Manager`
  }
})

export default router
