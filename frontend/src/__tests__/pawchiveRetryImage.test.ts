import { mount } from '@vue/test-utils'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import PawchiveRetryImage from '../components/external/pawchive/PawchiveRetryImage.vue'

const mountImage = (src = '/external/pawchive/media/ref?token=t') => mount(PawchiveRetryImage, {
  props: { src },
  attrs: { alt: '', class: 'cover' },
  slots: { fallback: '<span class="fallback">no preview</span>' },
})

describe('PawchiveRetryImage', () => {
  beforeEach(() => vi.useFakeTimers())
  afterEach(() => vi.useRealTimers())

  it('retries with backoff before showing the fallback', async () => {
    const wrapper = mountImage()
    expect(wrapper.get('img').attributes('src')).toBe('/external/pawchive/media/ref?token=t')
    expect(wrapper.get('img').classes()).toContain('cover')

    await wrapper.get('img').trigger('error')
    expect(wrapper.get('img').classes()).toContain('invisible')
    await vi.advanceTimersByTimeAsync(1499)
    expect(wrapper.get('img').attributes('src')).not.toContain('retry=')
    await vi.advanceTimersByTimeAsync(1)
    expect(wrapper.get('img').attributes('src')).toBe('/external/pawchive/media/ref?token=t&retry=1')
    expect(wrapper.get('img').classes()).not.toContain('invisible')

    await wrapper.get('img').trigger('error')
    await vi.advanceTimersByTimeAsync(4000)
    expect(wrapper.get('img').attributes('src')).toContain('retry=2')
    expect(wrapper.emitted('failed')).toBeUndefined()

    await wrapper.get('img').trigger('error')
    expect(wrapper.find('img').exists()).toBe(false)
    expect(wrapper.get('.fallback').text()).toBe('no preview')
    expect(wrapper.emitted('failed')).toHaveLength(1)
  })

  it('recovers when a retry loads', async () => {
    const wrapper = mountImage()
    await wrapper.get('img').trigger('error')
    await vi.advanceTimersByTimeAsync(1500)
    await wrapper.get('img').trigger('load')
    expect(wrapper.get('img').attributes('src')).toContain('retry=1')
    expect(wrapper.emitted('failed')).toBeUndefined()
  })

  it('starts over for a new source and shows the fallback without one', async () => {
    const wrapper = mountImage()
    await wrapper.get('img').trigger('error')
    await wrapper.setProps({ src: '/other' })
    await vi.advanceTimersByTimeAsync(5000)
    expect(wrapper.get('img').attributes('src')).toBe('/other')
    await wrapper.setProps({ src: '' })
    expect(wrapper.find('.fallback').exists()).toBe(true)
  })
})
