import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import axios from 'axios'
import DedupView from '../views/DedupView.vue'
import { dedupStore } from '../stores/dedupStore'
import type { DedupMediaSummary, DuplicateCandidatePair } from '../types'

const originalAdapter = axios.defaults.adapter
const clipboardDescriptor = Object.getOwnPropertyDescriptor(navigator, 'clipboard')
const commandDescriptor = Object.getOwnPropertyDescriptor(document, 'execCommand')
let wrapper: ReturnType<typeof mount> | undefined
const media = (id: number): DedupMediaSummary => ({
  id, title: `Copy fixture ${id}`, display_path: `/fixture/${id}.mp4`, media_type: 'video',
  extension: '.mp4', file_size: 1000, cover_path: null, duration: 60, width: 640,
  height: 360, page_count: null, is_missing: false, missing_since: null, duplicate_status: 'unique',
  favorite: false, rating: 0, source_url: null, source_site: null,
})
const pair: DuplicateCandidatePair = {
  id: 1, level: 'strong_duplicate', similarity: 0.99, reason: 'phash', status: 'pending',
  created_at: '', resolved_at: null, resolution_note: null, existing: media(1), candidate: media(2),
}
beforeEach(() => {
  vi.useFakeTimers()
  dedupStore.state.pairs = []
  dedupStore.state.summary = null
  dedupStore.state.errorMessage = ''
  dedupStore.setFilters({ level: '', status: 'pending', mediaType: '', sort: 'confidence' })
  Object.defineProperty(navigator, 'clipboard', { value: undefined, configurable: true })
  axios.defaults.adapter = async config => ({
    config, status: 200, statusText: 'OK', headers: {},
    data: config.url?.endsWith('/dedup/summary')
      ? { pending_pairs: 1, total_media: 2, fingerprinted: 2, unchecked: 0, failed: 0, checking: 0, queue_size: 0 }
      : { items: [pair], total: 1, limit: 20, offset: 0 },
  })
})
afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  axios.defaults.adapter = originalAdapter
  vi.clearAllTimers()
  vi.useRealTimers()
  if (clipboardDescriptor) Object.defineProperty(navigator, 'clipboard', clipboardDescriptor)
  else Reflect.deleteProperty(navigator, 'clipboard')
  if (commandDescriptor) Object.defineProperty(document, 'execCommand', commandDescriptor)
  else Reflect.deleteProperty(document, 'execCommand')
})
const openCopy = async () => {
  wrapper = mount(DedupView, { attachTo: document.body })
  await flushPromises()
  const expand = wrapper.findAll('button').find(button => button.text().includes('查看差异'))
  if (expand) await expand.trigger('click')
  const copy = wrapper.get('button[aria-label="复制左侧路径"]')
  ;(copy.element as HTMLButtonElement).focus()
  return copy
}

describe('duplicate paths copied from the actual comparison UI', () => {
  for (const mode of ['false', 'throw']) {
    it(`does not report success or leak a textarea when HTTP copying returns ${mode}`, async () => {
      Object.defineProperty(document, 'execCommand', { configurable: true, value: () => {
        if (mode === 'throw') throw new Error('fixture rejection')
        return false
      } })
      const copy = await openCopy()
      await copy.trigger('click')
      await flushPromises()
      expect(wrapper!.get('[role="alert"]').text()).toContain('复制失败')
      expect(copy.find('[class*="lucide-check"]').exists()).toBe(false)
      expect(document.querySelector('textarea')).toBeNull()
      expect(document.activeElement).toBe(copy.element)
    })
  }
  it('reports a successful HTTP fallback only after the browser confirms copying', async () => {
    const command = vi.fn(() => true)
    Object.defineProperty(document, 'execCommand', { configurable: true, value: command })
    const copy = await openCopy()
    await copy.trigger('click')
    await flushPromises()
    expect(command).toHaveBeenCalledWith('copy')
    expect(copy.find('[class*="lucide-check"]').exists()).toBe(true)
    expect(document.querySelector('textarea')).toBeNull()
    expect(document.activeElement).toBe(copy.element)
  })
  it('tries the HTTP fallback if secure clipboard permission is rejected', async () => {
    const writeText = vi.fn().mockRejectedValue(new Error('permission denied'))
    const command = vi.fn(() => true)
    Object.defineProperty(navigator, 'clipboard', { configurable: true, value: { writeText } })
    Object.defineProperty(document, 'execCommand', { configurable: true, value: command })
    const copy = await openCopy()
    await copy.trigger('click')
    await flushPromises()
    expect(writeText).toHaveBeenCalledWith('/fixture/1.mp4')
    expect(command).toHaveBeenCalledWith('copy')
    expect(copy.find('[class*="lucide-check"]').exists()).toBe(true)
  })
})
