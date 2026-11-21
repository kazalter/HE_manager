import { afterEach, describe, expect, it } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { createMemoryHistory, createRouter } from 'vue-router'
import CommandPalette from '../components/CommandPalette.vue'
import UiModal from '../components/ui/UiModal.vue'
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
