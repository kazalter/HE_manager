import { describe, it, expect, vi, beforeEach } from 'vitest'
import { mount, flushPromises } from '@vue/test-utils'

// Plain stub: vitest would also report a rejection the component already handled.
let respond: () => Promise<unknown> = async () => []
const calls: unknown[][] = []
vi.mock('../utils/assistantApi', () => ({
  getMediaCards: (...args: unknown[]) => {
    calls.push(args)
    return respond()
  },
}))

import MediaResults from '../components/assistant/MediaResults.vue'

const search = (ids: number[], total = ids.length) => ({
  tool_call_id: 'call-' + ids.join('-'),
  tool_name: 'search_media',
  result: {
    items: ids.map((id) => ({ id, title: '作品 ' + id, media_type: 'manga', tags: [] })),
    total,
  },
})
const full = (id: number) => ({
  id,
  title: '作品 ' + id,
  relative_path: 'x',
  media_type: 'manga',
  extension: '.cbz',
  file_size: 1,
  cover_path: 'cover_' + id + '.jpg',
  duration: null,
  width: null,
  height: null,
  page_count: 12,
  rating: 0,
  favorite: false,
  view_status: 'unviewed',
  progress: 0,
  last_opened_at: null,
  source_url: null,
  source_site: null,
  is_missing: false,
  missing_since: null,
  created_at: '2026-10-10T00:00:00',
  tags: [],
})

describe('assistant media results', () => {
  beforeEach(() => {
    calls.length = 0
  })

  it('loads covers for result ids and opens the clicked work', async () => {
    respond = async () => [full(2), full(1)]
    const wrapper = mount(MediaResults, { props: { results: [search([1, 2], 30)] as any } })
    expect(calls[0]?.[0]).toEqual([1, 2])
    expect(wrapper.text()).toContain('作品 1')
    await flushPromises()
    const srcs = wrapper.findAll('img').map((img) => img.attributes('src'))
    expect(srcs.some((src) => src?.includes('/thumbnails/cover_1.jpg'))).toBe(true)
    expect(srcs.some((src) => src?.includes('/thumbnails/cover_2.jpg'))).toBe(true)
    expect(wrapper.text()).toContain('共匹配 30 部')
    await wrapper.findAll('button.he-media-card')[1]!.trigger('click')
    expect(wrapper.emitted('open')).toEqual([[2]])
  })

  it('keeps cards usable when covers cannot be loaded', async () => {
    respond = async () => {
      throw new Error('offline')
    }
    const wrapper = mount(MediaResults, { props: { results: [search([5])] as any } })
    await flushPromises()
    expect(wrapper.text()).toContain('作品 5')
    expect(wrapper.find('.skeleton').exists()).toBe(false)
  })

  it('collapses long result lists behind a show-all toggle', async () => {
    respond = async () => []
    const ids = Array.from({ length: 14 }, (_, i) => i + 1)
    const wrapper = mount(MediaResults, { props: { results: [search(ids)] as any } })
    await flushPromises()
    expect(wrapper.findAll('button.he-media-card')).toHaveLength(10)
    const toggle = wrapper.findAll('button').find((b) => b.text().includes('显示全部 14 部'))!
    await toggle.trigger('click')
    expect(wrapper.findAll('button.he-media-card')).toHaveLength(14)
  })
})
