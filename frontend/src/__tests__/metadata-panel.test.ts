import { describe, it, expect } from 'vitest'
import { mount } from '@vue/test-utils'
import MetadataPanel from '../components/media-detail/MetadataPanel.vue'
import type { Media } from '../types'

describe('MetadataPanel component', () => {
  const sampleMedia: Media = {
    id: 101,
    title: 'Sample Video Title',
    relative_path: 'sample.mp4',
    media_type: 'video',
    extension: '.mp4',
    file_size: 1048576,
    cover_path: null,
    duration: 120,
    width: 1920,
    height: 1080,
    page_count: null,
    rating: 4,
    favorite: true,
    view_status: 'viewing',
    progress: 50,
    last_opened_at: null,
    source_url: 'https://example.com/source',
    source_site: 'test',
    is_missing: false,
    missing_since: null,
    created_at: '2026-01-01',
    tags: [
      { id: 1, name: 'Tag One', namespace: 'general', count: 5 },
      { id: 2, name: 'Artist Name', namespace: 'artist', count: 2 },
    ],
  }

  const defaultProps = {
    media: sampleMedia,
    coverUrl: 'http://localhost:8000/cover.jpg',
    mediaTypeLabel: '视频',
    videoProgressPercent: 50,
    mangaProgressPercent: 0,
    mangaProgressText: '0 / 0',
    mangaPageTotal: 0,
  }

  it('renders media title, tags and metadata correctly', () => {
    const wrapper = mount(MetadataPanel, {
      props: defaultProps,
    })

    expect(wrapper.text()).toContain('Tag One')
    expect(wrapper.text()).toContain('Artist Name')
    expect(wrapper.text()).toContain('视频')
    expect(wrapper.find('input[placeholder="添加标签"]').exists()).toBe(true)
  })

  it('emits addTag when input is submitted', async () => {
    const wrapper = mount(MetadataPanel, {
      props: defaultProps,
    })

    const input = wrapper.find('input[placeholder="添加标签"]')
    await input.setValue('New Tag')
    await input.trigger('keydown.enter')

    expect(wrapper.emitted('addTag')).toBeTruthy()
    expect(wrapper.emitted('addTag')?.[0]).toEqual(['New Tag'])
  })

  it('emits removeTag when remove button is clicked', async () => {
    const wrapper = mount(MetadataPanel, {
      props: defaultProps,
    })

    const removeBtn = wrapper.find('button[title="移除标签"]')
    expect(removeBtn.exists()).toBe(true)
    await removeBtn.trigger('click')

    expect(wrapper.emitted('removeTag')).toBeTruthy()
    expect(wrapper.emitted('removeTag')?.[0]).toEqual([1])
  })

  it('emits setRating when rating star is clicked', async () => {
    const wrapper = mount(MetadataPanel, {
      props: defaultProps,
    })

    const starButtons = wrapper.findAll('button[title$="星"]')
    expect(starButtons.length).toBe(5)
    await starButtons[4].trigger('click')

    expect(wrapper.emitted('setRating')).toBeTruthy()
    expect(wrapper.emitted('setRating')?.[0]).toEqual([5])
  })
})
