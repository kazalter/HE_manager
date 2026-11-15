import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import axios from 'axios'
import MetadataEnrichmentSettings from '../components/MetadataEnrichmentSettings.vue'

afterEach(() => vi.restoreAllMocks())

it('loads metadata stats and triggers local and external backfill jobs', async () => {
  const initialStats = {
    total_media: 100,
    tagged_media: 20,
    with_artist: 15,
    manga_total: 40,
    manga_profiled: 10,
    manga_wnacg_total: 30,
    manga_wnacg_with_sidecar: 2,
    audio_total: 5,
    audio_with_sidecar: 3,
    total_tags: 42,
  }
  const updatedStats = {
    ...initialStats,
    tagged_media: 85,
    with_artist: 80,
    manga_profiled: 40,
    total_tags: 120,
  }

  const getSpy = vi.spyOn(axios, 'get').mockResolvedValue({ data: initialStats })
  const postSpy = vi.spyOn(axios, 'post').mockImplementation(async (url: string) => {
    if (url.endsWith('/system/backfill-metadata')) {
      return {
        data: {
          checked: 100,
          updated: 65,
          tags_attached: 180,
          noise_tags_deleted: 12,
          stats: updatedStats,
        },
      }
    }
    if (url.endsWith('/system/backfill-external-metadata')) {
      return {
        data: {
          job_id: 'ext-job-1',
          status: 'running',
          total: 28,
          completed: 3,
          failed: 0,
          tags_attached: 19,
          current_title: 'Test Work',
          message: '正在抓取',
        },
      }
    }
    if (url.endsWith('/system/backfill-external-metadata/ext-job-1/cancel')) {
      return {
        data: {
          job_id: 'ext-job-1',
          status: 'canceled',
          total: 28,
          completed: 3,
          failed: 0,
          tags_attached: 19,
          current_title: null,
          message: '已取消',
        },
      }
    }
    return { data: {} }
  })

  const wrapper = mount(MetadataEnrichmentSettings)
  await flushPromises()

  expect(getSpy).toHaveBeenCalledWith(expect.stringContaining('/system/metadata/stats'))
  expect(wrapper.text()).toContain('20 / 100')
  expect(wrapper.text()).toContain('3 / 5')
  expect(wrapper.text()).toContain('有效标签共 42 个')

  const localBtn = wrapper.findAll('button').find((b) => b.text().includes('一键补充本地元数据'))!
  await localBtn.trigger('click')
  await flushPromises()

  expect(postSpy).toHaveBeenCalledWith(
    expect.stringContaining('/system/backfill-metadata'),
    null,
    expect.objectContaining({ params: { limit: 10000 } }),
  )
  expect(wrapper.text()).toContain('85 / 100')
  expect(wrapper.text()).toContain('清理噪声标签 12 个')

  const extBtn = wrapper.findAll('button').find((b) => b.text().includes('抓取 WNACG / ASMR 详情标签'))!
  await extBtn.trigger('click')
  await flushPromises()

  expect(postSpy).toHaveBeenCalledWith(
    expect.stringContaining('/system/backfill-external-metadata'),
    null,
    expect.objectContaining({
      params: {
        limit: 100,
        delay_seconds: 1.0,
        include_wnacg: true,
        include_asmr: true,
      },
    }),
  )
  expect(wrapper.text()).toContain('进度：3 / 28')

  const cancelBtn = wrapper.findAll('button').find((b) => b.text().includes('取消抓取'))!
  await cancelBtn.trigger('click')
  await flushPromises()
  expect(postSpy).toHaveBeenCalledWith(expect.stringContaining('/system/backfill-external-metadata/ext-job-1/cancel'))
})
