import { afterEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import ClockWeather from '../components/ClockWeather.vue'

afterEach(() => { vi.useRealTimers(); vi.unstubAllGlobals(); vi.restoreAllMocks(); localStorage.clear() })

describe('clock and weather', () => {
  it('updates the clock every second and loads weather for a saved location', async () => {
    vi.useFakeTimers()
    vi.setSystemTime(new Date('2026-10-29T01:00:00+08:00'))
    localStorage.setItem('he-weather-place', JSON.stringify({ name: '测试城市', latitude: 31.2, longitude: 121.4 }))
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ current: { temperature_2m: 21.4, weather_code: 3, is_day: 1, time: '2026-10-29T01:00' } }) })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ClockWeather)
    await Promise.resolve(); await Promise.resolve(); await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('测试城市')
    expect(wrapper.text()).toContain('21°')
    const before = wrapper.get('time').text()
    await vi.advanceTimersByTimeAsync(1000)
    expect(wrapper.get('time').text()).not.toBe(before)
    expect(fetchMock).toHaveBeenCalledOnce()
    wrapper.unmount()
  })

  it('offers city search when browser location is unavailable', async () => {
    vi.stubGlobal('isSecureContext', false)
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [{ name: '上海', latitude: 31.2, longitude: 121.4 }] }) })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ClockWeather)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('当前地址无法自动定位')
    await wrapper.get('input[aria-label="搜索城市"]').setValue('上海')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('上海')
    expect(fetchMock.mock.calls[0]?.[0]).toContain('geocoding-api.open-meteo.com')
    wrapper.unmount()
  })
})
