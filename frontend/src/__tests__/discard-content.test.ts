import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { flushPromises, mount } from '@vue/test-utils'
import { authState } from '../auth'
import DiscardContentDialog from '../components/DiscardContentDialog.vue'
import { executeDiscard, previewDiscard } from '../utils/discardApi'
vi.mock('../utils/discardApi', () => ({ previewDiscard: vi.fn(), executeDiscard: vi.fn(), formatBytes: () => '1 KB' }))
const preview = { title: 'Temporary test book', source_type: 'wnacg', preview_hash: 'a'.repeat(64), media_count: 1, file_size: 100,
  scope: '当前内容', message: '删除后不会重复下载', files: [{ relative_path: 'book', exists: true, is_directory: true }] }
const wrappers: ReturnType<typeof mount>[] = []
const setup = () => {
  const wrapper = mount(DiscardContentDialog, { props: { target: { kind: 'media', target_id: 1 } }, global: {
    stubs: { UiModal: { props: ['open'], template: '<div v-if="open"><slot/><slot name="footer"/></div>' } },
  } }); wrappers.push(wrapper); return wrapper
}
beforeEach(() => { authState.token = 'test-only-token'; vi.mocked(previewDiscard).mockResolvedValue(preview) })
afterEach(() => { wrappers.forEach(w => w.unmount()); wrappers.length = 0; vi.clearAllMocks() })
describe('explicit content deletion confirmation', () => {
  it('only previews until the user acknowledges and clicks delete', async () => {
    const w = setup(); await flushPromises()
    const button = () => w.findAll('button').find(b => b.text() === '删除并丢弃')!
    expect(executeDiscard).not.toHaveBeenCalled(); expect(button().attributes('disabled')).toBeDefined()
    vi.mocked(executeDiscard).mockResolvedValue({ id: 'test', title: preview.title, source_type: 'wnacg', status: 'discarded', discarded_at: '', media_count: 1, file_size: 100, media_ids: [1], cleanup_status: 'completed', cleanup_error: null })
    await w.get('input[type="checkbox"]').setValue(true); await button().trigger('click'); await flushPromises()
    expect(executeDiscard).toHaveBeenCalledOnce(); expect(executeDiscard).toHaveBeenCalledWith({kind:'media',target_id:1}, preview.preview_hash)
    expect(w.emitted('discarded')).toHaveLength(1)
  })
  it('cancel never calls the deletion endpoint', async () => {
    const w = setup(); await flushPromises(); await w.findAll('button').find(b => b.text() === '取消')!.trigger('click')
    expect(executeDiscard).not.toHaveBeenCalled(); expect(w.emitted('update:target')?.at(-1)).toEqual([null])
  })
  it('stale previews cannot replace the newly selected content', async () => {
    let finish!: (p: typeof preview) => void
    vi.mocked(previewDiscard).mockImplementationOnce(() => new Promise(resolve => { finish = resolve }))
    const w = setup(); await w.setProps({ target: {kind:'media',target_id:2} }); await flushPromises()
    finish({...preview,title:'Old response'}); await flushPromises()
    expect(w.text()).not.toContain('Old response'); expect(w.text()).toContain(preview.title)
  })
  it('conflicts clear the acknowledgement and require a fresh preview', async () => {
    const w = setup(); await flushPromises(); vi.mocked(executeDiscard).mockRejectedValue({ response: {data: {detail:'内容已变化'}} })
    await w.get('input[type="checkbox"]').setValue(true); await w.findAll('button').find(b => b.text() === '删除并丢弃')!.trigger('click'); await flushPromises()
    expect(w.text()).toContain('内容已变化'); expect(w.find('input[type="checkbox"]').exists()).toBe(false)
    expect(w.emitted('discarded')).toBeUndefined(); expect(w.text()).toContain('重新检查')
  })
})
