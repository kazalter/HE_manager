import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { computed, defineComponent, nextTick, ref } from 'vue'
import { useMediaProgress } from '../composables/useMediaProgress'
import type { Media } from '../types'

const wrappers: ReturnType<typeof mount>[] = []
afterEach(() => { wrappers.splice(0).forEach(wrapper => wrapper.unmount()) })

it('keeps queued manga saves attached to the old media after the viewer switches works', async () => {
  const media = ref({ id: 7, media_type: 'manga', progress: 0, page_count: 10, view_status: 'viewing' } as Media)
  const currentPage = ref(0)
  let releaseFirst!: () => void
  const blocked = new Promise<void>(resolve => { releaseFirst = resolve })
  const requests: { id: number; progress: number | undefined }[] = []
  // The production callback defaults to the media active when the queued callback runs.
  const updateMedia = vi.fn(async (payload: { progress?: number }, id = media.value.id) => {
    requests.push({ id, progress: payload.progress })
    if (requests.length === 1) await blocked
  })
  let progress!: ReturnType<typeof useMediaProgress>
  wrappers.push(mount(defineComponent({
    setup() {
      progress = useMediaProgress({
        media, currentPage, totalMangaPages: ref(10),
        isVideo: computed(() => false), isManga: computed(() => true),
        visibleMangaOnly: true, updateMedia, emitUpdated: () => {}, onVideoEnded: () => {},
      })
      return () => null
    },
  })))

  progress.visiblePage(1)
  const first = progress.flushProgress()
  await flushPromises()
  expect(requests).toEqual([{ id: 7, progress: 1 }])
  progress.visiblePage(2)
  const second = progress.flushProgress()
  await flushPromises()
  expect(requests).toHaveLength(1)

  media.value = { ...media.value, id: 8, progress: 0 }
  await nextTick()
  releaseFirst()
  await Promise.all([first, second])
  expect(requests).toEqual([{ id: 7, progress: 1 }, { id: 7, progress: 2 }])
  progress.visiblePage(3)
  await progress.flushProgress()
  expect(requests.at(-1)).toEqual({ id: 8, progress: 3 })
})
