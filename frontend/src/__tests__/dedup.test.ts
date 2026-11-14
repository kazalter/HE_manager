import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import axios, { type AxiosAdapter } from 'axios'
import DedupView from '../views/DedupView.vue'
import { dedupStore } from '../stores/dedupStore'

let wrapper: ReturnType<typeof mount> | undefined
const originalAdapter = axios.defaults.adapter
let scans = 0
let failedScan = false
let cleanedStale = 0
let bulkResolved = 0
const stats = {
  pending_pairs: 0, strong_duplicate: 0, suspected_duplicate: 0, weak_suspected: 0,
  checking: 0, queue_size: 0, worker_running: false,
  total_media: 12, fingerprinted: 2, unchecked: 10, failed: 1, stale_pairs: 0,
}

beforeEach(() => {
  vi.useFakeTimers()
  scans = 0
  failedScan = false
  cleanedStale = 0
  bulkResolved = 0
  stats.checking = 0
  stats.weak_suspected = 0
  stats.stale_pairs = 0
  stats.worker_running = false
  dedupStore.state.summary = null
  dedupStore.state.pairs = []
  dedupStore.state.errorMessage = ''
  dedupStore.setFilters({ level: '', status: 'pending', mediaType: '', sort: 'confidence' })
  axios.defaults.adapter = (async (config) => {
    if (config.method === 'post' && config.url?.endsWith('/dedup/candidates-cleanup-stale')) {
      cleanedStale++
      const deleted = stats.stale_pairs ?? 0
      stats.stale_pairs = 0
      return { data: { deleted }, status: 200, statusText: 'OK', headers: {}, config }
    }
    if (config.method === 'post' && config.url?.endsWith('/dedup/candidates-bulk-resolve')) {
      bulkResolved++
      const processed = stats.weak_suspected ?? 0
      stats.weak_suspected = 0
      stats.pending_pairs = 0
      return { data: { processed, skipped: 0 }, status: 200, statusText: 'OK', headers: {}, config }
    }
    if (config.method === 'post' && config.url?.endsWith('/dedup/recheck')) {
      if (failedScan) throw { response: { data: { detail: '无法启动检测' } } }
      scans++
      stats.checking = 12
      stats.worker_running = true
      return { data: { queued: 12, total: 12 }, status: 200, statusText: 'OK', headers: {}, config }
    }
    const data = config.url?.endsWith('/dedup/summary')
      ? { ...stats } : { items: [], total: 0, limit: 20, offset: 0 }
    return { data, status: 200, statusText: 'OK', headers: {}, config }
  }) as AxiosAdapter
})

afterEach(() => {
  wrapper?.unmount()
  wrapper = undefined
  axios.defaults.adapter = originalAdapter
  vi.useRealTimers()
})

describe('duplicate detection page', () => {
  it('shows incomplete detection instead of implying an empty library is duplicate-free', async () => {
    wrapper = mount(DedupView)
    await flushPromises()
    expect(wrapper.text()).toContain('10 项尚未建立指纹')
    expect(wrapper.text()).toContain('1 项检测失败')
    const start = wrapper.findAll('button').find(button => button.text().includes('检测全库'))
    expect(start).toBeDefined()
    await start!.trigger('click')
    await flushPromises()
    expect(scans).toBe(1)
    expect(wrapper.text()).toContain('检测进行中')
    expect(start!.attributes('disabled')).toBeDefined()
  })

  it('polls a running detection and stops polling after unmount', async () => {
    stats.checking = 12
    stats.worker_running = true
    wrapper = mount(DedupView)
    await flushPromises()
    expect(wrapper.text()).toContain('检测进行中')
    stats.checking = 0
    stats.worker_running = false
    await vi.advanceTimersByTimeAsync(3500)
    await flushPromises()
    expect(wrapper.text()).not.toContain('检测进行中')
    wrapper.unmount()
    wrapper = undefined
    expect(vi.getTimerCount()).toBe(0)
  })

  it('shows a scan error and permits retrying', async () => {
    failedScan = true
    wrapper = mount(DedupView)
    await flushPromises()
    const start = wrapper.findAll('button').find(button => button.text().includes('检测全库'))
    expect(start).toBeDefined()
    await start!.trigger('click')
    await flushPromises()
    expect(wrapper.find('[role="alert"]').text()).toContain('无法启动检测')
    expect(start!.attributes('disabled')).toBeUndefined()
  })

  it('supports cleaning stale pairs and bulk resolving weak duplicates', async () => {
    stats.stale_pairs = 5
    stats.weak_suspected = 8
    stats.pending_pairs = 8
    wrapper = mount(DedupView)
    await flushPromises()
    const cleanBtn = wrapper.findAll('button').find(b => b.text().includes('清理失效记录'))
    const bulkBtn = wrapper.findAll('button').find(b => b.text().includes('一键非重复低置信度'))
    expect(cleanBtn).toBeDefined()
    expect(bulkBtn).toBeDefined()
    await cleanBtn!.trigger('click')
    await flushPromises()
    await bulkBtn!.trigger('click')
    await flushPromises()
    expect(cleanedStale).toBe(1)
    expect(bulkResolved).toBe(1)
  })
})
