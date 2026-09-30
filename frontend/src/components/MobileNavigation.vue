<script setup lang="ts">
import { computed, reactive, watch } from 'vue'
import { useRoute } from 'vue-router'
import { Compass, Ellipsis, Library, Star } from 'lucide-vue-next'
const route = useRoute()
const saved = reactive({ library: '/', favorites: '/?favorite=true', discover: '/external' })
try { Object.assign(saved, JSON.parse(sessionStorage.getItem('he_mobile_tabs') || '{}')) } catch { /* optional */ }
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
</script>
<template>
  <nav class="he-mobile-nav" aria-label="手机主导航">
    <router-link v-for="item in items" :key="item.key" :to="item.to" :aria-current="section === item.key ? 'page' : undefined" :class="{ active: section === item.key }">
      <component :is="item.icon" :size="22" aria-hidden="true" />
      <span>{{ item.title }}</span>
    </router-link>
  </nav>
</template>
