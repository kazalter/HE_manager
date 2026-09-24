import { computed, defineComponent, h, ref } from 'vue'
import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import type { Media } from '../types'
import { useMediaProgress } from '../composables/useMediaProgress'
import { nextVideo } from '../utils/videoSequence'

const media = (id: number, type: Media['media_type'], missing = false) => ({
  id, media_type: type, is_missing: missing, progress: 0, duration: 100, view_status: 'unviewed',
}) as Media

describe('video playback', () => {
  it('chooses playable videos in order and shuffle modes', () => {
    const items = [media(1, 'video'), media(2, 'image'), media(3, 'video', true),
      media(4, 'manga'), media(5, 'video')]
    expect(nextVideo(items, 1, 'order')?.id).toBe(5)
    expect(nextVideo(items, 5, 'order')).toBeUndefined()
    expect(nextVideo(items, 1, 'shuffle', () => 0)?.id).toBe(5)
    expect(nextVideo(items, 5, 'shuffle', () => 0)?.id).toBe(1)
  })

  it('waits for an older progress write before sending the newer position', async () => {
    const currentMedia = ref(media(1, 'video'))
    const resolves: Array<() => void> = []
    const writes: number[] = []
    const updateMedia = vi.fn((payload: { progress?: number }) => {
      writes.push(payload.progress ?? -1)
      return new Promise<void>(resolve => resolves.push(resolve))
    })
    let progress!: ReturnType<typeof useMediaProgress>
    const Harness = defineComponent({
      setup() {
        progress = useMediaProgress({
          media: currentMedia, currentPage: ref(0), totalMangaPages: ref(null),
          isVideo: computed(() => true), isManga: computed(() => false),
          updateMedia, emitUpdated: () => {}, onVideoEnded: () => {},
        })
        return () => h('div')
      },
    })
    const wrapper = mount(Harness)
    const video = document.createElement('video')
    Object.defineProperty(video, 'duration', { value: 100 })
    progress.bindVideo(video)
    video.currentTime = 10
    const first = progress.saveVideoProgress(true)
    video.currentTime = 20
    const second = progress.saveVideoProgress(true)
    await flushPromises()
    expect(writes).toEqual([10])
    resolves.shift()?.()
    await first
    await flushPromises()
    expect(writes).toEqual([10, 20])
    resolves.shift()?.()
    await second
    progress.unbindVideo()
    wrapper.unmount()
  })
})
