import { afterEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { flushPromises, mount, type VueWrapper } from '@vue/test-utils'
import PawchivePanel from '../components/external/pawchive/PawchivePanel.vue'

vi.mock('vue-router', () => ({
  useRoute: () => ({ path: '/external', query: {} }),
  useRouter: () => ({ replace: vi.fn() }),
}))
const creator = { service: 'fanbox', creator_id: '12', creator_name: 'Test artist', source_url: 'https://pawchive.pw/fanbox/user/12' }
let wrapper: VueWrapper | undefined
afterEach(() => { wrapper?.unmount(); wrapper = undefined; vi.restoreAllMocks() })

async function openFavorite() {
  vi.spyOn(axios, 'get').mockImplementation(async url => ({ data: String(url).endsWith('/account/status') ? { connected: false }
    : String(url).endsWith('/creators') ? { items: [creator], total: 1, page: 1, page_size: 30, services: ['fanbox'], popularity_available: true }
      : { creator_tags: true, image: true, video: ['mp4'] } }))
  wrapper = mount(PawchivePanel, { attachTo: document.body, global: { stubs: { Teleport: true } } })
  await flushPromises()
  expect(wrapper.find('[role="dialog"]').exists()).toBe(false)
  await wrapper.findAll('nav[aria-label="Pawchive 作者范围"] button')[1]!.trigger('click')
  await flushPromises()
  await wrapper.get('button[aria-label="收藏作者 Test artist"]').trigger('click')
  expect(wrapper.get('[role="dialog"]').text()).toContain('登录后继续收藏作者 Test artist')
}

async function submitLogin() {
  await wrapper!.get('[role="dialog"] input[autocomplete="username"]').setValue('test')
  await wrapper!.get('[role="dialog"] input[type="password"]').setValue('test')
  await wrapper!.get('[role="dialog"] form').trigger('submit')
  await flushPromises()
}

describe('Pawchive favorite login continuation', () => {
  it('resumes the requested favorite exactly once after login', async () => {
    await openFavorite()
    vi.spyOn(axios, 'post').mockResolvedValue({ data: { connected: true, items: [] } })
    const put = vi.spyOn(axios, 'put').mockResolvedValue({ data: {} })
    await submitLogin()
    expect(put).toHaveBeenCalledTimes(1)
    expect(String(put.mock.calls[0]![0])).toContain('/account/favorites/fanbox/12')
    expect(wrapper!.find('[role="dialog"]').exists()).toBe(false)
    expect(wrapper!.find('button[aria-label="取消收藏作者 Test artist"]').exists()).toBe(true)
  })

  it('does not toggle off an author already saved in the newly logged-in account', async () => {
    await openFavorite()
    vi.spyOn(axios, 'post').mockResolvedValue({ data: { connected: true, items: [creator] } })
    const put = vi.spyOn(axios, 'put'), remove = vi.spyOn(axios, 'delete')
    await submitLogin()
    expect(put).not.toHaveBeenCalled()
    expect(remove).not.toHaveBeenCalled()
    expect(wrapper!.find('[role="dialog"]').exists()).toBe(false)
  })

  it('canceling settings clears the action before a later manual login', async () => {
    await openFavorite()
    await wrapper!.get('[role="dialog"] button[aria-label="关闭"]').trigger('click')
    await wrapper!.get('header[aria-label="Pawchive 状态与设置"] button').trigger('click')
    vi.spyOn(axios, 'post').mockResolvedValue({ data: { connected: true, items: [] } })
    const put = vi.spyOn(axios, 'put')
    await submitLogin()
    expect(put).not.toHaveBeenCalled()
  })

  it('honors cancellation while the login request is still in flight', async () => {
    await openFavorite()
    let finish!: (data: unknown) => void
    vi.spyOn(axios, 'post').mockReturnValue(new Promise(resolve => { finish = resolve }))
    const put = vi.spyOn(axios, 'put')
    await submitLogin()
    await wrapper!.get('[role="dialog"] button[aria-label="关闭"]').trigger('click')
    finish({ data: { connected: true, items: [] } })
    await flushPromises()
    expect(put).not.toHaveBeenCalled()
  })
})
