import { createRouter, createWebHashHistory } from 'vue-router'
import HomeView from '../views/HomeView.vue'

const router = createRouter({
  history: createWebHashHistory(),
  routes: [
    {
      path: '/',
      name: 'home',
      component: HomeView
    },
    {
      path: '/type/:mediaType',
      name: 'type-filter',
      component: HomeView,
      props: true
    },
    {
      path: '/settings',
      name: 'settings',
      component: () => import('../views/SettingsView.vue')
    },
    {
      path: '/external',
      name: 'external-favorites',
      component: () => import('../views/ExternalFavoritesView.vue')
    },
    {
      path: '/dedup',
      name: 'dedup',
      component: () => import('../views/DedupView.vue')
    },
    {
      path: '/users',
      name: 'users',
      component: () => import('../views/UsersView.vue')
    },
    {
      // Dashboard stats: chart-heavy overview, distribution, activity, attention.
      path: '/stats',
      name: 'stats',
      component: () => import('../views/StatsView.vue')
    },
    {
      // Unified creators list (X authors + manga artists).
      path: '/creators',
      name: 'creators',
      component: () => import('../views/CreatorsView.vue')
    },
    {
      // Creator detail (same view, branches on route.params.screenName).
      path: '/creators/:screenName',
      name: 'creator-detail',
      component: () => import('../views/CreatorsView.vue'),
      props: true
    },
    {
      path: '/tags',
      name: 'tags',
      component: () => import('../views/TagsView.vue')
    },
    {
      path: '/recommend',
      name: 'manga-recommend',
      component: () => import('../views/MangaRecommendView.vue')
    },
    {
      path: '/bd2-spine',
      name: 'bd2-spine',
      component: () => import('../views/Bd2SpineView.vue')
    },
    {
      path: '/bd2-spine/embed',
      name: 'bd2-spine-embed',
      component: () => import('../views/EmbedSpineView.vue')
    }
  ]
})

export default router
