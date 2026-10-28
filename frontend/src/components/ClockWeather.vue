<script setup lang="ts">
import { computed, onBeforeUnmount, onMounted, ref } from 'vue'
import { Cloud, CloudDrizzle, CloudFog, CloudLightning, CloudRain, CloudSnow, CloudSun, MapPin, Moon, RefreshCw, Sun } from 'lucide-vue-next'

withDefaults(defineProps<{ compact?: boolean }>(), { compact: false })
type Place = { name: string; latitude: number; longitude: number; admin1?: string; country?: string; auto?: boolean }
type Weather = { temperature: number; code: number; isDay: boolean; observedAt: string }
const now = ref(new Date())
const place = ref<Place | null>(null)
const weather = ref<Weather | null>(null)
const message = ref('正在定位…')
const searchText = ref('')
const searchResults = ref<Place[]>([])
const searching = ref(false)
let clockTimer: number | undefined, weatherTimer: number | undefined
let weatherRequest = 0, searchRequest = 0, locationRequest = 0, disposed = false
const dateText = computed(() => new Intl.DateTimeFormat('zh-CN', { year: 'numeric', month: 'numeric', day: 'numeric', weekday: 'short' }).format(now.value))
const timeText = computed(() => new Intl.DateTimeFormat('zh-CN', { hour: '2-digit', minute: '2-digit', second: '2-digit', hourCycle: 'h23' }).format(now.value))
const description = computed(() => {
  const w = weather.value
  if (!w) return ''
  if (w.code === 0) return '晴'
  if (w.code <= 3) return w.code === 3 ? '阴' : '多云'
  if (w.code === 45 || w.code === 48) return '雾'
  if ([51, 53, 55, 56, 57].includes(w.code)) return '毛毛雨'
  if ([61, 63, 65, 66, 67, 80, 81, 82].includes(w.code)) return '雨'
  if ([71, 73, 75, 77, 85, 86].includes(w.code)) return '雪'
  if ([95, 96, 99].includes(w.code)) return '雷雨'
  return '天气'
})
const weatherIcon = computed(() => {
  const w = weather.value
  if (!w) return Cloud
  if (w.code === 0) return w.isDay ? Sun : Moon
  if (w.code <= 3) return CloudSun
  if (w.code === 45 || w.code === 48) return CloudFog
  if (w.code >= 95) return CloudLightning
  if ([71, 73, 75, 77, 85, 86].includes(w.code)) return CloudSnow
  if ([51, 53, 55, 56, 57].includes(w.code)) return CloudDrizzle
  return CloudRain
})
const refreshWeather = async () => {
  const current = place.value
  if (!current) return
  const request = ++weatherRequest
  try {
    const params = new URLSearchParams({ latitude: String(current.latitude), longitude: String(current.longitude), current: 'temperature_2m,weather_code,is_day', timezone: 'auto' })
    const response = await fetch(`https://api.open-meteo.com/v1/forecast?${params}`)
    if (!response.ok) throw new Error('weather unavailable')
    const data = await response.json()
    const values = data.current
    if (!values || !Number.isFinite(values.temperature_2m) || !Number.isFinite(values.weather_code)) throw new Error('invalid weather')
    if (disposed || request !== weatherRequest) return
    weather.value = { temperature: values.temperature_2m, code: values.weather_code, isDay: values.is_day === 1, observedAt: values.time }
    message.value = ''
  } catch {
    if (!disposed && request === weatherRequest) { weather.value = null; message.value = '天气暂时不可用' }
  }
}
const selectPlace = (value: Place) => {
  locationRequest++
  place.value = value; weather.value = null; message.value = '正在获取天气…'; searchResults.value = []
  try { localStorage.setItem('he-weather-place', JSON.stringify(value)) } catch { /* optional */ }
  void refreshWeather()
}
const locate = () => {
  const request = ++locationRequest
  if (!window.isSecureContext || !navigator.geolocation) { message.value = '当前地址无法自动定位，请选择城市'; return }
  message.value = '正在定位…'
  navigator.geolocation.getCurrentPosition(position => {
    if (!disposed && request === locationRequest) selectPlace({ name: '当前位置', latitude: position.coords.latitude, longitude: position.coords.longitude, auto: true })
  }, () => { if (!disposed && request === locationRequest) message.value = '定位不可用，请选择城市' }, { timeout: 10000, maximumAge: 1800000 })
}
const searchPlaces = async () => {
  const name = searchText.value.trim()
  if (name.length < 2) { searchResults.value = []; message.value = '请输入至少两个字符'; return }
  const request = ++searchRequest
  searching.value = true
  try {
    const params = new URLSearchParams({ name, count: '8', language: 'zh', format: 'json' })
    const response = await fetch(`https://geocoding-api.open-meteo.com/v1/search?${params}`)
    if (!response.ok) throw new Error('search unavailable')
    const data = await response.json()
    if (disposed || request !== searchRequest) return
    searchResults.value = (data.results || []).filter((p: Place) => p.name && Number.isFinite(p.latitude) && Number.isFinite(p.longitude))
    message.value = searchResults.value.length ? '' : '没有找到城市，请尝试其他名称'
  } catch {
    if (!disposed && request === searchRequest) message.value = '城市搜索暂时不可用'
  } finally { if (request === searchRequest) searching.value = false }
}
onMounted(() => {
  clockTimer = window.setInterval(() => { now.value = new Date() }, 1000)
  try {
    const saved = JSON.parse(localStorage.getItem('he-weather-place') || 'null') as Place | null
    if (saved && saved.name && Number.isFinite(saved.latitude) && Number.isFinite(saved.longitude)) place.value = saved
  } catch { /* optional */ }
  if (place.value) {
    void refreshWeather()
    if (place.value.auto && window.isSecureContext) locate()
  }
  else locate()
  weatherTimer = window.setInterval(() => { void refreshWeather() }, 30 * 60 * 1000)
})
onBeforeUnmount(() => { disposed = true; weatherRequest++; searchRequest++; locationRequest++; window.clearInterval(clockTimer); window.clearInterval(weatherTimer) })
</script>

<template>
  <div class="he-clock-weather" :class="compact ? 'he-clock-weather--compact' : 'he-clock-weather--panel'">
    <div class="he-clock" aria-label="当前日期和时间">
      <span class="he-clock-date">{{ dateText }}</span>
      <time class="he-clock-time" :datetime="now.toISOString()">{{ timeText }}</time>
    </div>
    <details class="he-weather">
      <summary class="he-weather-trigger focus-ring" :title="weather ? `${place?.name} ${description} ${Math.round(weather.temperature)}°C` : message">
        <component :is="weatherIcon" :size="18" aria-hidden="true" />
        <span v-if="weather" class="he-weather-label">{{ Math.round(weather.temperature) }}° <span class="he-weather-place">{{ place?.name }}</span></span>
        <span v-else>天气</span>
      </summary>
      <div class="he-weather-popover">
        <div class="flex items-center justify-between gap-3">
          <span class="font-medium text-ink">{{ place?.name || '天气位置' }}</span>
          <button type="button" class="he-weather-action focus-ring" @click="locate"><MapPin :size="14" />自动定位</button>
        </div>
        <p v-if="weather" class="mt-2 text-meta text-muted">{{ description }} · {{ Math.round(weather.temperature) }}°C <button type="button" class="he-weather-action focus-ring" aria-label="刷新天气" @click="refreshWeather"><RefreshCw :size="13" /></button></p>
        <p v-if="message" role="status" class="mt-2 text-meta text-subtle">{{ message }}</p>
        <form class="mt-3 flex gap-2" @submit.prevent="searchPlaces">
          <input v-model="searchText" class="min-w-0 flex-1 rounded-lg border border-line bg-surface-2 px-2.5 py-2 text-meta text-ink focus-ring" aria-label="搜索城市" placeholder="输入城市名称" />
          <button class="he-weather-action focus-ring" :disabled="searching" type="submit">{{ searching ? '搜索中' : '搜索' }}</button>
        </form>
        <ul v-if="searchResults.length" class="mt-2 max-h-40 overflow-y-auto">
          <li v-for="result in searchResults" :key="`${result.latitude},${result.longitude}`"><button type="button" class="w-full rounded-lg px-2 py-2 text-left text-meta text-muted hover:bg-surface-2 focus-ring" @click="selectPlace(result)">{{ [result.name, result.admin1, result.country].filter(Boolean).join(' · ') }}</button></li>
        </ul>
        <p class="mt-3 text-caption text-subtle">天气数据：<a href="https://open-meteo.com/" target="_blank" rel="noopener noreferrer" class="underline">Open-Meteo</a></p>
      </div>
    </details>
  </div>
</template>

<style scoped>
.he-clock-weather { display: flex; align-items: center; gap: 12px; color: rgb(var(--color-muted)); }
.he-clock-weather--compact { flex: none; }
.he-clock-weather--panel { justify-content: space-between; padding: 14px 16px; border: 1px solid rgb(var(--color-line)); border-radius: 16px; background: rgb(var(--color-surface)); }
.he-clock { display: flex; flex-direction: column; line-height: 1.25; white-space: nowrap; }
.he-clock-date { font-size: 11px; color: rgb(var(--color-subtle)); }
.he-clock-time { font-size: 14px; font-weight: 600; font-variant-numeric: tabular-nums; color: rgb(var(--color-ink)); }
.he-clock-weather--panel .he-clock-date { font-size: 12px; }
.he-clock-weather--panel .he-clock-time { font-size: 20px; }
.he-weather { position: relative; }
.he-weather-trigger { display: flex; align-items: center; gap: 6px; min-height: 40px; padding: 0 8px; border-radius: 8px; cursor: pointer; font-size: 12px; white-space: nowrap; list-style: none; }
.he-weather-trigger::-webkit-details-marker { display: none; }
.he-weather-label { display: flex; gap: 4px; align-items: center; }
.he-weather-place { display: inline-block; max-width: 64px; overflow: hidden; text-overflow: ellipsis; }
.he-weather-trigger:hover { background: rgb(var(--color-surface-2)); color: rgb(var(--color-ink)); }
.he-weather-popover { position: absolute; z-index: 80; top: calc(100% + 8px); right: 0; width: min(288px, calc(100vw - 32px)); padding: 14px; border: 1px solid rgb(var(--color-line-strong)); border-radius: 14px; background: rgb(var(--color-surface)); box-shadow: var(--he-shadow-pop); }
.he-weather-action { display: inline-flex; align-items: center; gap: 4px; padding: 6px; border-radius: 6px; color: rgb(var(--color-muted)); font-size: 12px; }
.he-weather-action:hover { background: rgb(var(--color-surface-2)); color: rgb(var(--color-ink)); }
</style>
