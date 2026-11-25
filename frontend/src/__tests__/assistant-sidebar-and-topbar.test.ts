import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from '../App.vue'
import NavigationRail from '../components/NavigationRail.vue'
import AssistantSidebar from '../components/AssistantSidebar.vue'
import ModelSwitcher from '../components/assistant/ModelSwitcher.vue'
import { authState } from '../auth'
import { assistantPanelStore } from '../stores/assistantPanelStore'
import type { User } from '../types'

const wrappers: ReturnType<typeof mount>[] = []

afterEach(() => {
  for (const wrapper of wrappers.splice(0)) wrapper.unmount()
  assistantPanelStore.reset()
  authState.ready = false
  authState.token = ''
  authState.user = null
  document.body.innerHTML = ''
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('top-right clock/weather and right-side assistant sidebar', () => {
  const adminUser: User = { id: 1, username: 'admin', is_admin: true, is_active: true, created_at: '' }

  it('removes ClockWeather from NavigationRail and toggles assistant sidebar without navigating', async () => {
    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div />' } },
        { path: '/assistant', component: { template: '<div />' } },
        { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
      ],
    })
    await testRouter.push('/')

    const wrapper = mount(NavigationRail, {
      props: { user: adminUser, collapsed: false },
      global: { plugins: [testRouter] },
    })
    wrappers.push(wrapper)

    expect(wrapper.find('.he-clock-weather').exists()).toBe(false)
    const assistantBtn = wrapper.findAll('button').find(b => b.text().includes('媒体库管家'))
    expect(assistantBtn).toBeTruthy()
    await assistantBtn!.trigger('click')
    expect(assistantPanelStore.state.open).toBe(true)
    expect(testRouter.currentRoute.value.path).toBe('/')

    await assistantBtn!.trigger('click')
    expect(assistantPanelStore.state.open).toBe(false)
  })

  it('renders ClockWeather in App.vue top-right bar and opens right assistant sidebar as an overlay without compressing main', async () => {
    vi.stubGlobal('isSecureContext', false)
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(
      String(url).endsWith('/status')
        ? { enabled: true, busy: false, active_run_id: null }
        : { items: [], total: 0, offset: 0, has_more: false, pending_count: 0 },
    ))))

    Object.defineProperty(window, 'innerWidth', { configurable: true, writable: true, value: 1440 })
    authState.ready = true
    authState.token = 'admin-token'
    authState.user = adminUser

    const testRouter = createRouter({
      history: createMemoryHistory(),
      routes: [
        { path: '/', component: { template: '<div class="stub-home">Home</div>' } },
        { path: '/:pathMatch(.*)*', component: { template: '<div />' } },
      ],
    })
    await testRouter.push('/')

    const wrapper = mount(App, {
      global: { plugins: [testRouter] },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    const rail = wrapper.get('aside.he-nav-rail')
    expect(rail.find('.he-clock-weather').exists()).toBe(false)

    const topbar = wrapper.get('header.he-shell-topbar')
    expect(topbar.find('.he-clock-weather').exists()).toBe(true)

    const toggleBtn = topbar.get('button[aria-controls="he-assistant-sidebar"]')
    expect(toggleBtn.attributes('aria-expanded')).toBe('false')
    await toggleBtn.trigger('click')
    await flushPromises()

    expect(assistantPanelStore.state.open).toBe(true)
    expect(toggleBtn.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.he-studio-shell').classes()).not.toContain('is-assistant-docked-open')

    const sidebar = document.querySelector<HTMLElement>('aside#he-assistant-sidebar')
    expect(sidebar).not.toBeNull()
    expect(sidebar?.getAttribute('role')).toBe('dialog')
    expect(sidebar?.textContent).toContain('媒体库管家')

    sidebar?.querySelector<HTMLButtonElement>('button[aria-label="关闭媒体库管家"]')?.click()
    await flushPromises()
    expect(assistantPanelStore.state.open).toBe(false)
  })

  it('closes AssistantSidebar slide-over drawer on Escape and close button', async () => {
    authState.token = 'admin-token'
    authState.user = adminUser
    vi.stubGlobal('fetch', vi.fn(async (url: string) => new Response(JSON.stringify(
      String(url).endsWith('/status')
        ? { enabled: true, busy: false, active_run_id: null }
        : { items: [], total: 0, offset: 0, has_more: false, pending_count: 0 },
    ))))

    const wrapper = mount(AssistantSidebar, {
      props: { open: true },
      attachTo: document.body,
    })
    wrappers.push(wrapper)
    await flushPromises()

    const drawer = document.querySelector('#he-assistant-sidebar')
    expect(drawer).not.toBeNull()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(wrapper.emitted('close')).toHaveLength(1)
  })

  it('expands ModelSwitcher, switches preset, and closes with Escape', async () => {
    const wrapper = mount(ModelSwitcher, {
      props: {
        modelConfig: {
          model: 'deepseek-flash',
          display_model: 'DeepSeek-V4.1-Flash',
          base_url: 'https://api.deepseek.com/v1',
          key_configured: true,
          thinking_disabled: true,
          presets: [
            {
              id: 'deepseek-flash',
              label: 'DeepSeek-V4.1-Flash',
              model: 'deepseek-flash',
              base_url: 'https://api.deepseek.com/v1',
              key_configured: true,
              thinking_disabled: true,
              custom: false,
            },
            {
              id: 'deepseek-v4-pro',
              label: 'DeepSeek-V4-Pro',
              model: 'deepseek-v4-pro',
              base_url: 'https://api.deepseek.com/v1',
              key_configured: true,
              thinking_disabled: false,
              custom: false,
            },
          ],
        },
        compact: true,
      },
      attachTo: document.body,
    })
    wrappers.push(wrapper)

    const trigger = wrapper.get('button[aria-haspopup="dialog"]')
    expect(trigger.text()).toContain('DeepSeek-V4.1-Flash')
    expect(trigger.attributes('aria-expanded')).toBe('false')

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    const dialog = wrapper.get('[role="dialog"]')
    expect(dialog.text()).toContain('DeepSeek-V4-Pro')

    const proBtn = dialog.findAll('button').find(b => b.text().includes('DeepSeek-V4-Pro'))!
    await proBtn.trigger('click')
    expect(wrapper.emitted('selectPreset')).toEqual([['deepseek-v4-pro']])
    expect(trigger.attributes('aria-expanded')).toBe('false')

    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    await wrapper.get('button[role="switch"]').trigger('click')
    expect(wrapper.emitted('toggleThinking')).toEqual([[false]])
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await flushPromises()
    expect(trigger.attributes('aria-expanded')).toBe('false')
  })
})
