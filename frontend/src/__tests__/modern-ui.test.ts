import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import axios from 'axios'
import CommandPalette from '../components/CommandPalette.vue'
import NavigationRail from '../components/NavigationRail.vue'
import UiModal from '../components/ui/UiModal.vue'
import HomeView from '../views/HomeView.vue'
import SettingsView from '../views/SettingsView.vue'
import { authState } from '../auth'
import { applyDensity, cycleDensity, densityState, initDensity } from '../density'
import router, { resolveRouteTitle } from '../router'
import type { User } from '../types'

declare const __dirname: string
const fsModule = 'node:fs'
const { readFileSync } = await import(/* @vite-ignore */ fsModule) as { readFileSync(path: string, encoding: 'utf8'): string }
const styleCss = readFileSync(`${__dirname}/../style.css`, 'utf8')

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  document.body.innerHTML = ''
  localStorage.clear()
  delete document.documentElement.dataset.density
  document.documentElement.style.removeProperty('--density')
  applyDensity('comfortable')
  vi.restoreAllMocks()
})

describe('modern UI foundation & CSS guidance compliance', () => {
  it('uses modern CSS features without banned global animation resets or oklch neutral mixes', () => {
    expect(styleCss).toContain('interpolate-size: allow-keywords;')
    expect(styleCss).toContain('scrollbar-color:')
    expect(styleCss).toContain('@media (forced-colors: active)')
    expect(styleCss).toContain('color-mix(in oklab,')
    expect(styleCss).not.toMatch(/color-mix\(\s*in\s+oklch/)
    expect(styleCss).not.toMatch(/\*\s*,\s*\*::before\s*,\s*\*::after\s*\{[^}]*animation-duration:\s*\.?01ms/)
    expect(styleCss).toContain('dialog:modal')
    expect(styleCss).toContain('dialog::backdrop')
    expect(styleCss).toContain(':where([data-density="spacious"])')
    expect(styleCss).toContain('@container style(--density: spacious)')
    expect(styleCss).toContain('grid-template-rows: subgrid')
    expect(styleCss).toContain('@supports (container-type: scroll-state)')
  })

  it('resolves descriptive document titles for library routes', async () => {
    await router.push('/type/manga')
    expect(resolveRouteTitle(router.currentRoute.value)).toBe('漫画')
    await router.push('/?favorite=true')
    expect(resolveRouteTitle(router.currentRoute.value)).toBe('我的收藏')
    await router.push('/settings')
    expect(resolveRouteTitle(router.currentRoute.value)).toBe('设置')
  })
})

describe('UiModal native <dialog> integration', () => {
  it('renders a native <dialog> with aria-labelledby, description, and closes on Escape/button', async () => {
    const wrapper = mount(UiModal, {
      props: {
        open: true,
        title: '确认操作',
        description: '测试描述信息',
      },
      slots: { default: '<p>内容体</p>' },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    const dialog = document.querySelector('dialog')
    expect(dialog).not.toBeNull()
    expect(dialog?.getAttribute('aria-labelledby')).toBeTruthy()
    expect(dialog?.getAttribute('aria-describedby')).toBeTruthy()
    expect(document.body.textContent).toContain('确认操作')
    expect(document.body.textContent).toContain('测试描述信息')

    const closeBtn = document.querySelector<HTMLButtonElement>('dialog button[aria-label="关闭"]')
    expect(closeBtn).not.toBeNull()
    closeBtn?.click()
    await flushPromises()
    expect(wrapper.emitted('update:open')?.at(-1)).toEqual([false])
  })
})

describe('CommandPalette navigation and search', () => {
  const adminUser: User = { id: 1, username: 'admin', is_admin: true, is_active: true, created_at: '' }
  const memberUser: User = { id: 2, username: 'member', is_admin: false, is_active: true, created_at: '' }

  it('filters destinations by role and navigates to library search on custom query', async () => {
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/settings', component: { template: '<div />' } },
        { path: '/stats', component: { template: '<div />' } },
      ],
    })
    await testRouter.push('/')

    const memberWrapper = mount(CommandPalette, {
      props: { open: true, user: memberUser },
      global: { plugins: [testRouter] },
      attachTo: document.body,
    })
    wrappers.push(memberWrapper)
    await flushPromises()
    expect(document.body.textContent).toContain('统计看板')
    expect(document.body.textContent).not.toContain('用户管理')
    memberWrapper.unmount()

    const adminWrapper = mount(CommandPalette, {
      props: { open: true, user: adminUser },
      global: { plugins: [testRouter] },
      attachTo: document.body,
    })
    wrappers.push(adminWrapper)
    await flushPromises()
    expect(document.body.textContent).toContain('用户管理')

    const input = document.querySelector<HTMLInputElement>('dialog input[type="search"]')!
    input.value = '猫娘'
    input.dispatchEvent(new Event('input'))
    await flushPromises()

    expect(document.body.textContent).toContain('在媒体库中搜索「猫娘」')
    input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }))
    await flushPromises()
    expect(testRouter.currentRoute.value.fullPath).toBe('/?search=%E7%8C%AB%E5%A8%98')
  })
})

describe('visual density reactivity and persistence', () => {
  it('sets data-density, --density custom property, persists to localStorage, and cycles modes', () => {
    applyDensity('spacious')
    expect(densityState.density).toBe('spacious')
    expect(document.documentElement.dataset.density).toBe('spacious')
    expect(document.documentElement.style.getPropertyValue('--density')).toBe('spacious')
    expect(localStorage.getItem('he_visual_density')).toBe('spacious')

    cycleDensity()
    expect(densityState.density).toBe('compact')
    expect(document.documentElement.dataset.density).toBe('compact')

    localStorage.setItem('he_visual_density', 'spacious')
    initDensity()
    expect(densityState.density).toBe('spacious')
  })
})

describe('NavigationRail layout navigation and role gating', () => {
  it('renders grouped destinations by role and emits collapse and palette events', async () => {
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/downloads', component: { template: '<div />' } },
        { path: '/settings', component: { template: '<div />' } },
        { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
      ],
    })
    await testRouter.push('/')

    const memberUser: User = { id: 2, username: 'reader', is_admin: false, is_active: true, created_at: '' }
    const memberWrapper = mount(NavigationRail, {
      props: { user: memberUser, collapsed: false },
      global: { plugins: [testRouter] },
    })
    wrappers.push(memberWrapper)

    expect(memberWrapper.text()).toContain('下载任务')
    expect(memberWrapper.text()).not.toContain('设置')
    expect(memberWrapper.text()).not.toContain('用户管理')

    await memberWrapper.get('button[aria-label="收起侧边导航"]').trigger('click')
    expect(memberWrapper.emitted('toggleCollapse')).toHaveLength(1)

    await memberWrapper.get('button[aria-label="打开命令面板搜索或跳转"]').trigger('click')
    expect(memberWrapper.emitted('openCommandPalette')).toHaveLength(1)
  })
})

describe('HomeView slide-over filter drawer and active chips', () => {
  it('opens filter drawer from toolbar, closes on Escape, and surfaces active filter chips inline', async () => {
    authState.user = { id: 1, username: 'reader', is_admin: false, is_active: true, created_at: '' }
    vi.spyOn(axios, 'get').mockImplementation(async url => ({
      data: String(url).endsWith('/tags') ? [{ id: 1, name: '风景', namespace: 'general', count: 3 }] : [],
      headers: { 'x-total-count': '0' },
    }))
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [{ path: '/', component: { template: '<div />' } }],
    })
    await testRouter.push('/?source=local&min_rating=4')
    const wrapper = mount(HomeView, {
      global: { plugins: [testRouter], stubs: { MediaDetail: true } },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    expect(wrapper.text()).toContain('来源: 本地')
    expect(wrapper.text()).toContain('评分: 4★+')
    expect(wrapper.findAll('button').some(b => b.text().includes('清除筛选'))).toBe(true)

    const trigger = wrapper.get('button[aria-controls="he-filter-drawer"]')
    await trigger.trigger('click')
    await flushPromises()
    const drawer = document.querySelector<HTMLElement>('#he-filter-drawer')
    expect(drawer).not.toBeNull()
    expect(drawer?.textContent).toContain('布局舒适度')
    expect(drawer?.textContent).toContain('风景')

    drawer?.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }))
    await flushPromises()
    expect(document.querySelector('#he-filter-drawer')).toBeNull()
  })
})

describe('SettingsView visual density choice cards', () => {
  it('updates global density state when choosing a radio card option', async () => {
    authState.user = { id: 1, username: 'admin', is_admin: true, is_active: true, created_at: '' }
    vi.spyOn(axios, 'get').mockResolvedValue({ data: [] })
    const wrapper = mount(SettingsView, {
      global: {
        stubs: {
          AssistantModelSettings: true,
          MetadataEnrichmentSettings: true,
          WallpaperSettings: true,
          ColorModeSelect: true,
        },
      },
    })
    wrappers.push(wrapper)
    await flushPromises()

    const spaciousRadio = wrapper.get('input[type="radio"][name="visual-density"][value="spacious"]')
    await spaciousRadio.setValue(true)
    await spaciousRadio.trigger('change')
    expect(densityState.density).toBe('spacious')
    expect(document.documentElement.dataset.density).toBe('spacious')
  })
})
