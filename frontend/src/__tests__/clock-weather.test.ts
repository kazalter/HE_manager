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
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [{ name: '杭州', latitude: 30.2, longitude: 120.1, admin1: '浙江' }] }) })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ClockWeather)
    await wrapper.vm.$nextTick()
    expect(wrapper.text()).toContain('当前地址无法自动定位')
    await wrapper.get('input[aria-label="搜索城市"]').setValue('杭州')
    await wrapper.get('form').trigger('submit')
    await flushPromises()
    expect(wrapper.text()).toContain('杭州')
    expect(fetchMock.mock.calls[0]?.[0]).toContain('geocoding-api.open-meteo.com')
    wrapper.unmount()
  })

  it('treats 湖北 as a province and searches a selected city within 湖北', async () => {
    vi.stubGlobal('isSecureContext', false)
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => ({ results: [
      { name: '武汉', admin1: '湖北', admin2: '武汉市', country: '中国', latitude: 30.58, longitude: 114.27, population: 10000000 },
      { name: '武汉', admin1: '内蒙古', country: '中国', latitude: 49, longitude: 117 },
    ] }) })
    vi.stubGlobal('fetch', fetchMock)
    const wrapper = mount(ClockWeather)
    await wrapper.get('input[aria-label="搜索城市"]').setValue('湖北省')
    await wrapper.get('form').trigger('submit')
    expect(wrapper.text()).toContain('请选择省内城市')
    expect(wrapper.text()).toContain('武汉 · 湖北')
    expect(wrapper.text()).toContain('荆门 · 湖北')
    expect(fetchMock).not.toHaveBeenCalled()
    const city = wrapper.findAll('button').find(button => button.text() === '武汉 · 湖北')!
    await city.trigger('click'); await flushPromises()
    expect(fetchMock.mock.calls[0]?.[0]).toContain('name=Wuhan')
    expect(wrapper.text()).toContain('武汉 · 武汉市 · 湖北 · 中国')
    expect(wrapper.text()).not.toContain('内蒙古')
    wrapper.unmount()
  })

  it('opens the weather panel and closes it with Escape while restoring focus', async () => {
    vi.stubGlobal('isSecureContext', false)
    const wrapper = mount(ClockWeather, { attachTo: document.body })
    const trigger = wrapper.get('button[aria-expanded]')
    expect(trigger.attributes('aria-expanded')).toBe('false')
    await trigger.trigger('click')
    expect(trigger.attributes('aria-expanded')).toBe('true')
    expect(wrapper.get('.he-weather-popover').attributes('inert')).toBeUndefined()
    document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape' }))
    await wrapper.vm.$nextTick()
    expect(trigger.attributes('aria-expanded')).toBe('false')
    expect(wrapper.get('.he-weather-popover').attributes('inert')).toBeDefined()
    expect(document.activeElement).toBe(trigger.element)
    wrapper.unmount()
  })
})
