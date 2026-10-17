import { describe, expect, it } from 'vitest'
import { defineComponent, ref } from 'vue'
import { mount } from '@vue/test-utils'
import UiSlider from '../components/ui/UiSlider.vue'

describe('shared range control', () => {
 it('commits the native position when input and change precede the parent render', () => {
  const committed: number[] = []
  const wrapper = mount(defineComponent({
   components: { UiSlider },
   setup: () => ({ value: ref(3), commit: (value: number) => committed.push(value) }),
   template: '<UiSlider v-model="value" label="播放位置" @commit="commit" />',
  }))
  const input = wrapper.get('input').element
  input.value = '20'
  input.dispatchEvent(new Event('input', { bubbles: true }))
  input.dispatchEvent(new Event('change', { bubbles: true }))
  expect(committed).toEqual([20])
  wrapper.unmount()
 })
})
