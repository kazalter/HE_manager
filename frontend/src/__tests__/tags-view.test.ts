import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import axios from 'axios'
import TagsView from '../views/TagsView.vue'

afterEach(() => vi.restoreAllMocks())

it('supports namespace filtering, minCount toggle, sorting, and per-group truncation', async () => {
  const sampleTags = [
    { id: 1, name: '单次画师', namespace: 'artist', count: 1 },
    { id: 2, name: '高频画师', namespace: 'artist', count: 12 },
    ...Array.from({ length: 85 }, (_, idx) => ({
      id: 100 + idx,
      name: `通用标签${idx + 1}`,
      namespace: 'general',
      count: idx + 2,
    })),
  ]

  vi.spyOn(axios, 'get').mockResolvedValue({ data: sampleTags })

  const wrapper = mount(TagsView, {
    global: {
      stubs: {
        'router-link': { template: '<a><slot /></a>' },
      },
    },
  })
  await flushPromises()

  // Truncates general group to 80 by default and offers expand button
  expect(wrapper.text()).toContain('显示其余 5 个通用标签')
  expect(wrapper.text()).toContain('高频画师')

  // Expand remaining items in general group
  const expandBtn = wrapper.findAll('button').find((b) => b.text().includes('显示其余 5 个通用标签'))!
  await expandBtn.trigger('click')
  expect(wrapper.text()).toContain('仅显示前 80 个')

  // Toggle "仅看常用 (≥2)" hides count=1 tag
  const minBtn = wrapper.findAll('button').find((b) => b.text().includes('仅看常用'))!
  await minBtn.trigger('click')
  expect(wrapper.text()).not.toContain('单次画师')
  expect(wrapper.text()).toContain('高频画师')

  // Namespace chip filter
  const artistTab = wrapper.findAll('button').find((b) => b.text().includes('作者 2'))!
  await artistTab.trigger('click')
  expect(wrapper.text()).toContain('高频画师')
  expect(wrapper.text()).not.toContain('通用标签85')
})
