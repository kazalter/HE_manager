import { afterEach, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import axios from 'axios'
import AssistantModelSettings from '../components/AssistantModelSettings.vue'

afterEach(() => vi.restoreAllMocks())
it('preserves a stored API key when saving model settings with the key field empty', async () => {
  const status = { deepseek_configured: true, key_saved: true, env_key_present: false, model: 'm', base_url: 'https://example.com' }
  vi.spyOn(axios, 'get').mockResolvedValue({ data: status })
  const save = vi.spyOn(axios, 'put').mockResolvedValue({ data: status })
  const wrapper = mount(AssistantModelSettings)
  await flushPromises()
  expect(wrapper.text()).toContain('已配置 API Key')
  await wrapper.findAll('input')[1]!.setValue('new-model')
  await wrapper.findAll('button')[0]!.trigger('click')
  await flushPromises()
  expect(save).toHaveBeenCalledWith(expect.any(String), { api_key: undefined, model: 'new-model', base_url: 'https://example.com' })
  expect(wrapper.text()).toContain('已保存配置')
})
