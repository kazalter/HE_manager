import { afterEach, beforeEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { reactive } from 'vue'

const host = vi.hoisted(() => ({ l2dUpdateStart: vi.fn(), l2dUpdateStatus: vi.fn(), wallpaperStart: vi.fn() }))
vi.mock('../desktop', () => ({
  desktopBridge: host,
  desktopSession: reactive({ generation: 'test' }),
  desktopState: reactive({ platform: 'win32' }),
}))
import Live2dView from '../views/Live2dView.vue'

beforeEach(() => { sessionStorage.clear(); vi.useFakeTimers(); host.l2dUpdateStatus.mockResolvedValue({ running: false, message: '', failures: [] }) })
afterEach(() => { vi.useRealTimers(); vi.clearAllMocks() })

it('keeps a dismissed progress panel closed during polling and lets the user reopen it', async () => {
  host.l2dUpdateStart.mockResolvedValue({ running: true, message: '正在检查', failures: [] })
  const wrapper = mount(Live2dView)
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text().includes('继续解包'))!.trigger('click')
  await flushPromises()
  expect(wrapper.get('[aria-label="解包状态"]').text()).toContain('正在检查')
  await wrapper.get('[aria-label="关闭解包提示"]').trigger('click')
  host.l2dUpdateStatus.mockResolvedValue({ running: true, message: '正在解包 1/2', failures: [] })
  await vi.advanceTimersByTimeAsync(1500)
  expect(wrapper.find('[aria-label="解包状态"]').exists()).toBe(false)
  await wrapper.findAll('button').find(button => button.text().includes('查看进度'))!.trigger('click')
  expect(wrapper.get('[aria-label="解包状态"]').text()).toContain('正在解包 1/2')
  await wrapper.get('[aria-label="关闭解包提示"]').trigger('click')
  host.l2dUpdateStatus.mockResolvedValue({ running: false, message: '完成：新增 2 个', failures: [] })
  await vi.advanceTimersByTimeAsync(1500)
  expect(wrapper.find('[aria-label="解包状态"]').exists()).toBe(false)
  await wrapper.get('[aria-label="查看解包结果"]').trigger('click')
  expect(wrapper.get('[aria-label="解包状态"]').text()).toContain('完成：新增 2 个')
  wrapper.unmount()
})

it('keeps a start error visible until the user closes or retries', async () => {
  host.l2dUpdateStart.mockRejectedValueOnce(new Error('请先使用管理员账号登录'))
  const wrapper = mount(Live2dView)
  await flushPromises()
  await wrapper.findAll('button').find(button => button.text().includes('继续解包'))!.trigger('click')
  await flushPromises()
  await vi.advanceTimersByTimeAsync(1500)
  expect(wrapper.get('[aria-label="解包状态"]').text()).toContain('请先使用管理员账号登录')
  await wrapper.get('[aria-label="关闭解包提示"]').trigger('click')
  expect(wrapper.find('[aria-label="解包状态"]').exists()).toBe(false)
  wrapper.unmount()
})
