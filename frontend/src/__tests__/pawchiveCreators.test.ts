import { afterEach, describe, expect, it, vi } from 'vitest'
import axios from 'axios'
import { flushPromises, mount } from '@vue/test-utils'
import { usePawchiveCreators } from '../composables/usePawchiveCreators'
import { parsePawchiveCreator } from '../utils/pawchiveCreator'
import PawchiveAuthors from '../components/external/pawchive/PawchiveAuthors.vue'
import PawchiveCreatorCard from '../components/external/pawchive/PawchiveCreatorCard.vue'
import type { PawchiveCreatorPage } from '../types/pawchive'

const creator = { service: 'patreon', creator_id: '1', creator_name: 'Test artist', source_url: 'https://pawchive.pw/patreon/user/1', favorite_count: 0 }
const page = (name = 'Test artist'): PawchiveCreatorPage => ({ items: [{ ...creator, creator_name: name }],
  total: 1, page: 1, page_size: 30, has_more: false, services: ['patreon'], applied_sort: 'popular',
  popularity_available: true, fetched_at: '2026-10-26T00:00:00Z', stale: false })
afterEach(() => vi.restoreAllMocks())

describe('author directory', () => {
  it('aborts previous searches and ignores out-of-order responses', async () => {
    let finish!: (value: { data: PawchiveCreatorPage }) => void
    const old = new Promise<{ data: PawchiveCreatorPage }>(resolve => { finish = resolve })
    const get = vi.spyOn(axios, 'get').mockReturnValueOnce(old as never).mockResolvedValueOnce({ data: { ...page('new'), page: 2 } })
    const directory = usePawchiveCreators()
    const pending = directory.search({ query: 'old', page: 8 })
    await directory.search({ query: 'new', page: 3, service: 'patreon', sort: 'relevance' })
    expect(get.mock.calls[0]![1]!.signal!.aborted).toBe(true)
    finish({ data: page('old') })
    await pending
    expect(directory.items.value[0]!.creator_name).toBe('new')
    expect(directory.page.value).toBe(2)
    expect(directory.query.value).toBe('new')
    directory.dispose()
  })

  it('shows failure and can retry the same filters', async () => {
    const get = vi.spyOn(axios, 'get').mockRejectedValueOnce(new Error('offline')).mockResolvedValueOnce({ data: page() })
    const directory = usePawchiveCreators()
    await directory.search({ query: 'cat', service: 'fanbox' })
    expect(directory.status.value).toBe('error')
    expect(directory.items.value).toEqual([])
    await directory.load()
    expect(directory.status.value).toBe('ready')
    expect(get.mock.calls[1]![1]!.params).toMatchObject({ q: 'cat', service: 'fanbox', page: 1 })
  })

  it('public discovery supports search, opening, favorites, and keeps its filters across tabs', async () => {
    const get = vi.spyOn(axios, 'get').mockResolvedValue({ data: page() })
    const wrapper = mount(PawchiveAuthors, { props: { favorites: [], favoritesLoading: false, accountConnected: false, favoriteBusyKeys: [] } })
    expect(get).not.toHaveBeenCalled()
    await wrapper.findAll('nav button')[1]!.trigger('click')
    await flushPromises()
    expect(wrapper.text()).toContain('热门作者')
    expect(wrapper.text()).toContain('0 人收藏')
    await wrapper.get('input').setValue('test')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(get.mock.calls.at(-1)![1]!.params).toMatchObject({ q: 'test', sort: 'relevance' })
    await wrapper.get('select[aria-label="作者平台"]').setValue('patreon')
    await flushPromises()
    await wrapper.findAll('nav button')[0]!.trigger('click')
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('')
    await wrapper.findAll('nav button')[1]!.trigger('click')
    expect((wrapper.get('select').element as HTMLSelectElement).value).toBe('patreon')
    await wrapper.get('button[aria-label="查看作者 Test artist"]').trigger('click')
    expect(wrapper.emitted('openCreator')![0]![0]).toMatchObject(creator)
    const favorite = wrapper.get('button[aria-label="收藏作者 Test artist"]')
    expect(favorite.attributes('disabled')).toBeUndefined()
    await favorite.trigger('click')
    expect(wrapper.emitted('favorite')).toHaveLength(1)
    await wrapper.get('input').setValue('https://pawchive.pw/fanbox/user/123')
    const callCount = get.mock.calls.length
    await wrapper.get('form').trigger('submit')
    expect(get).toHaveBeenCalledTimes(callCount)
    expect(wrapper.emitted('openCreator')!.at(-1)![0]).toMatchObject({ service: 'fanbox', creator_id: '123' })
    wrapper.unmount()
  })

  it('does not invent a count when the source omits it', () => {
    const wrapper = mount(PawchiveCreatorCard, { props: { creator: { ...creator, favorite_count: null }, favorite: false } })
    expect(wrapper.text()).not.toContain('人收藏')
    wrapper.unmount()
  })

  it('recognizes author links and service/ID without accepting other hosts', () => {
    expect(parsePawchiveCreator('patreon/12')).toEqual({ service: 'patreon', creatorId: '12' })
    expect(parsePawchiveCreator('https://pawchive.pw/fanbox/user/12?x=1')).toEqual({ service: 'fanbox', creatorId: '12' })
    expect(parsePawchiveCreator('https://pawchive.pw.evil/fanbox/user/12')).toBeNull()
    expect(parsePawchiveCreator('https://evil/fanbox/user/12')).toBeNull()
  })
})
